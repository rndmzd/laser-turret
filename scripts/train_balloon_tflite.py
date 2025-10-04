import argparse
import csv
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


def log(msg: str):
    print(msg, flush=True)


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def create_voc_annotation(xml_path: Path, image_filename: str, width: int, height: int, objects):
    ann = ET.Element('annotation')

    folder = ET.SubElement(ann, 'folder')
    folder.text = xml_path.parent.parent.name  # train/valid/test

    filename = ET.SubElement(ann, 'filename')
    filename.text = image_filename

    size = ET.SubElement(ann, 'size')
    w = ET.SubElement(size, 'width')
    w.text = str(width)
    h = ET.SubElement(size, 'height')
    h.text = str(height)
    d = ET.SubElement(size, 'depth')
    d.text = '3'

    segmented = ET.SubElement(ann, 'segmented')
    segmented.text = '0'

    for obj in objects:
        name = obj['class']
        xmin = max(0, int(round(obj['xmin'])))
        ymin = max(0, int(round(obj['ymin'])))
        xmax = min(width - 1, int(round(obj['xmax'])))
        ymax = min(height - 1, int(round(obj['ymax'])))

        # Skip invalid boxes
        if xmax <= xmin or ymax <= ymin:
            continue

        o = ET.SubElement(ann, 'object')
        n = ET.SubElement(o, 'name')
        n.text = name
        pose = ET.SubElement(o, 'pose')
        pose.text = 'Unspecified'
        truncated = ET.SubElement(o, 'truncated')
        truncated.text = '0'
        difficult = ET.SubElement(o, 'difficult')
        difficult.text = '0'

        bnd = ET.SubElement(o, 'bndbox')
        x1 = ET.SubElement(bnd, 'xmin')
        x1.text = str(xmin)
        y1 = ET.SubElement(bnd, 'ymin')
        y1.text = str(ymin)
        x2 = ET.SubElement(bnd, 'xmax')
        x2.text = str(xmax)
        y2 = ET.SubElement(bnd, 'ymax')
        y2.text = str(ymax)

    tree = ET.ElementTree(ann)
    tree.write(xml_path, encoding='utf-8', xml_declaration=True)


def convert_split_csv_to_voc(split_dir: Path, label_name: str = 'balloon') -> Path:
    """Convert Roboflow CSV annotations to Pascal VOC XML files under split_dir/annotations."""
    csv_path = split_dir / '_annotations.csv'
    if not csv_path.exists():
        raise FileNotFoundError(f'Annotations CSV not found: {csv_path}')

    ann_out_dir = split_dir / 'annotations'
    ensure_dir(ann_out_dir)

    # Group boxes by filename
    by_file = defaultdict(list)
    with csv_path.open('r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                fname = row['filename']
                width = int(float(row['width']))
                height = int(float(row['height']))
                cls = row.get('class', label_name) or label_name
                xmin = float(row['xmin'])
                ymin = float(row['ymin'])
                xmax = float(row['xmax'])
                ymax = float(row['ymax'])
            except Exception as e:
                raise RuntimeError(f'Invalid row in {csv_path}: {row}\nError: {e}')

            by_file[fname].append({
                'width': width,
                'height': height,
                'class': cls,
                'xmin': xmin,
                'ymin': ymin,
                'xmax': xmax,
                'ymax': ymax,
            })

    # Write one XML per image
    count = 0
    for fname, boxes in by_file.items():
        # Some CSVs include width/height per row; assume same for all rows of same image
        width = int(boxes[0]['width'])
        height = int(boxes[0]['height'])
        xml_name = Path(fname).with_suffix('.xml').name
        xml_path = ann_out_dir / xml_name
        create_voc_annotation(xml_path, fname, width, height, boxes)
        count += 1

    log(f'Converted {count} annotations in {split_dir}')
    return ann_out_dir


def main():
    ap = argparse.ArgumentParser(description='Train EfficientDet-Lite0 balloon detector and export TFLite')
    ap.add_argument('--dataset', type=str, default=str(Path('training') / 'Balloon detection.v3i.tensorflow'), help='Path to Roboflow TF dataset dir containing train/valid/test')
    ap.add_argument('--output', type=str, default=str(Path('models') / 'tflite'), help='Export directory for .tflite')
    ap.add_argument('--epochs', type=int, default=40, help='Training epochs')
    ap.add_argument('--batch-size', type=int, default=16, help='Batch size')
    ap.add_argument('--model-name', type=str, default='balloon_lite0', help='Output TFLite base filename (without extension)')
    args = ap.parse_args()

    dataset_dir = Path(args.dataset)
    if not dataset_dir.exists():
        raise FileNotFoundError(f'Dataset directory not found: {dataset_dir}')

    train_dir = dataset_dir / 'train'
    valid_dir = dataset_dir / 'valid'
    if not train_dir.exists() or not valid_dir.exists():
        raise FileNotFoundError('Expected train/ and valid/ subfolders in dataset')

    # 1) Convert CSV to Pascal VOC XML
    train_ann_dir = convert_split_csv_to_voc(train_dir, label_name='balloon')
    valid_ann_dir = convert_split_csv_to_voc(valid_dir, label_name='balloon')

    # 2) Load Model Maker and train EfficientDet-Lite0
    try:
        from tflite_model_maker import object_detector
        import tensorflow as tf  # noqa: F401
    except Exception as e:
        log('ERROR: Training dependencies missing. Install with:')
        log('  pip install -r training/requirements-train.txt')
        raise

    log('Loading Pascal VOC datasets...')
    label_map = {'balloon': 0}
    train_data = object_detector.DataLoader.from_pascal_voc(
        str(train_dir), str(train_ann_dir), label_map=label_map
    )
    valid_data = object_detector.DataLoader.from_pascal_voc(
        str(valid_dir), str(valid_ann_dir), label_map=label_map
    )

    log('Creating EfficientDet-Lite0 spec...')
    spec = object_detector.EfficientDetLite0Spec()

    log('Starting training...')
    model = object_detector.create(
        train_data,
        model_spec=spec,
        validation_data=valid_data,
        epochs=args.epochs,
        batch_size=args.batch_size,
        train_whole_model=True,
    )

    # 3) Export TFLite
    output_dir = Path(args.output)
    ensure_dir(output_dir)
    tflite_path = output_dir / f'{args.model_name}.tflite'

    log(f'Exporting TFLite to {tflite_path} ...')
    model.export(export_dir=str(output_dir), tflite_filename=f'{args.model_name}.tflite')

    log('Done.')
    log('Next steps:')
    log(f"  - Set tflite_model = {args.model_name} in laserturret.conf [Detection]")
    log('  - Start the app and switch to TensorFlow Lite in the UI or config')


if __name__ == '__main__':
    main()
