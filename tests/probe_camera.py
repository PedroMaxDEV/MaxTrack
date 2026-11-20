"""Explicit local hardware check. Does not save or transmit camera images."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import mediapipe as mp
import numpy as np
from maxtrack import estimate_pose, fallback_pose

index=int(sys.argv[1]) if len(sys.argv)>1 else 0
report={'camera':index,'frames':0,'faces':0,'finite_poses':0}
cap=cv2.VideoCapture(index,cv2.CAP_DSHOW)
try:
    if not cap.isOpened():
        cap.release();cap=cv2.VideoCapture(index,cv2.CAP_MSMF)
    report['opened']=cap.isOpened()
    if report['opened']:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,640);cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
        with mp.solutions.face_mesh.FaceMesh(max_num_faces=1,refine_landmarks=False) as mesh:
            deadline=time.monotonic()+8
            while time.monotonic()<deadline and report['frames']<60:
                ok,frame=cap.read()
                if not ok:break
                report['frames']+=1
                frame=cv2.flip(frame,1)
                result=mesh.process(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
                if result.multi_face_landmarks:
                    report['faces']+=1
                    face=result.multi_face_landmarks[0]
                    pose=estimate_pose(face,frame.shape[1],frame.shape[0])
                    if pose is None or not np.isfinite(pose).all() or np.abs(pose).max()>80:pose=fallback_pose(face)
                    if pose is not None and np.isfinite(pose).all():report['finite_poses']+=1
finally:cap.release()
Path('build/camera-probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
