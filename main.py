import os
import argparse
import cv2

from tqdm import tqdm
from detectron2 import model_zoo
from detectron2.engine import DefaultPredictor
from detectron2.config import get_cfg
from detectron2.utils.visualizer import Visualizer
from detectron2.data.datasets import register_coco_instances
from detectron2.data import DatasetCatalog, MetadataCatalog

from src.trainers import MyTrainer


TO_PREDICT_DIR = "to_predict"
PREDICTIONS_DIR = "predictions"


def _parse_args() -> argparse.Namespace:
    usage_message = """
                    Script for training a panels detector.
                    """

    parser = argparse.ArgumentParser(usage=usage_message)

    parser.add_argument("--mode", "-m", type=str, default="eval",
                        help="Mode (train, eval, draw_seg)")
    parser.add_argument("--dry", action="store_true", default=False)
    parser.add_argument("--batch_size", "-bs", type=int, default=2,
                        help="Batch size")
    parser.add_argument("--epochs", "-ep", type=int, default=2,
                        help="Training epochs")
    parser.add_argument("--learning_rate", "-lr", type=float, default=0.0002,
                        help="Training epochs")
    parser.add_argument("--checkpoint", "-tr", type=str, default=None,
                        help="Model weights path")
    parser.add_argument("--train_dataset", "-tr", type=str, default="acmd_v2",
                        help="Train dataset name")
    parser.add_argument("--test_dataset", "-te", type=str, default="comics_panels_annotations",
                        help="Test dataset name")
    parser.add_argument("--datasets_dir", "-dsdir", type=str, default="./datasets/",
                        help="Directory with all the datasets")
    parser.add_argument("--output_dir", "-od", type=str, default="output/",
                        help="Output directory")

    return parser.parse_args()


def get_base_cfg(args, dry: bool = False):
    cfg = get_cfg()
    cfg.merge_from_file(model_zoo.get_config_file("COCO-InstanceSegmentation/mask_rcnn_X_101_32x8d_FPN_3x.yaml"))
    cfg.DATALOADER.NUM_WORKERS = 1
    cfg.MODEL.WEIGHTS = model_zoo.get_checkpoint_url("COCO-InstanceSegmentation/mask_rcnn_X_101_32x8d_FPN_3x.yaml")
    cfg.SOLVER.IMS_PER_BATCH = args.batch_size
    cfg.INPUT.MIN_SIZE_TRAIN = (800, 600)
    cfg.INPUT.MAX_SIZE_TRAIN = 1200
    cfg.SOLVER.BASE_LR = args.learning_rate
    cfg.SOLVER.NUM_GPUS = 1
    
    if dry:
        cfg.SOLVER.MAX_ITER = 1
    else:
        single_iteration = cfg.SOLVER.NUM_GPUS * cfg.SOLVER.IMS_PER_BATCH
        iterations_for_one_epoch = 8035 // single_iteration
        cfg.SOLVER.MAX_ITER = iterations_for_one_epoch * args.epochs
    
    cfg.TEST.EVAL_PERIOD = 1000
    cfg.SOLVER.CHECKPOINT_PERIOD = 1000
    cfg.MODEL.ROI_HEADS.BATCH_SIZE_PER_IMAGE = (
        128
    ) 
    cfg.MODEL.ROI_HEADS.NUM_CLASSES = 1
    return cfg


def train(cfg, train_dataset: str, test_dataset: str):
    cfg.DATASETS.TRAIN = (train_dataset,)
    cfg.DATASETS.TEST = (test_dataset,)
    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)
    trainer = MyTrainer(cfg)
    trainer.resume_or_load(resume=False)
    trainer.train()
    

def evaluate(cfg, test_dataset: str, model_weights: str):
    cfg.MODEL.WEIGHTS = os.path.join(cfg.OUTPUT_DIR, model_weights)
    cfg.DATASETS.TEST = (test_dataset,)
    trainer = MyTrainer(cfg)
    trainer.resume_or_load(resume=True)
    metrics = MyTrainer.test(cfg, trainer.model)    


def draw_seg(cfg, test_dataset: str, model_weights: str):
    predictor = DefaultPredictor(cfg)
    cfg.MODEL.WEIGHTS = os.path.join(cfg.OUTPUT_DIR, model_weights)
    cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = 0.9

    out_dir = os.path.join(cfg.OUTPUT_DIR, cfg.DATASETS.TEST[0] + "_out")
    os.makedirs(out_dir, exist_ok=True)
    
    cpa_metadata = MetadataCatalog.get(test_dataset)
    dataset_dicts = DatasetCatalog.get(test_dataset)

    for d in tqdm(dataset_dicts):
        img = cv2.imread(d["file_name"])
        outputs = predictor(img)
        v = Visualizer(img[:, :, ::-1],
                    scale=0.8, 
                    # instance_mode=ColorMode.IMAGE_BW  
        )
        vis = v.draw_instance_predictions(outputs["instances"].to("cpu"))
        cv2.imwrite(f"{out_dir}/{d['image_id']}.jpg", vis.get_image()[:, :, ::-1])


def main(args: argparse.Namespace):
    register_coco_instances(args.train_dataset,
                            {},
                            "/home/smasip/Projectes/artificial_manga_panel_dataset/{args.train_dataset}/labels.json",
                            "/home/smasip/Projectes/artificial_manga_panel_dataset/{args.train_dataset}/data"
                            )
    register_coco_instances(args.test_dataset,
                            {},
                            "./{args.datasets_dir}/{args.test_dataset}/labels.json",
                            "./{args.datasets_dir}/{args.test_dataset}/data",
                            )    
    
    cfg = get_base_cfg(args)

    if args.mode == "train":
        train(cfg, args.train_dataset, args.test_dataset)
    elif args.mode == "eval":
        assert args.model_weights is not None
        evaluate(cfg, args.test_dataset, os.path.join(cfg.OUTPUT_DIR, args.checkpoint))
    elif args.mode == "draw_seg":
        assert args.model_weights is not None
        draw_seg(cfg, args.test_dataset, os.path.join(cfg.OUTPUT_DIR, args.checkpoint))
    else:
        raise Exception("Unknown mode.")


if __name__ == "__main__":
    args = _parse_args()
    main(args)
