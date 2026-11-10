"""MaxTrack 0.9: local USB webcam head tracking for OpenTrack UDP input."""
import json, math, os, queue, socket, struct, threading, time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import mediapipe as mp
import numpy as np
from pynput import keyboard

BASE = Path(os.environ.get('APPDATA', str(Path.home()))) / 'MaxTrack'
BASE.mkdir(parents=True, exist_ok=True)
CONFIG = BASE / 'config.json'
POINTS = (1, 152, 33, 263, 61, 291)
MODEL = np.array([(0,0,0),(0,-63.6,-12.5),(-43.3,32.7,-26),(43.3,32.7,-26),(-28.9,-28.9,-24.1),(28.9,-28.9,-24.1)], dtype=np.float64)
DEFAULT = dict(camera=0, sensitivity_x=2.0, sensitivity_y=1.6, deadzone=1.3,
               smoothing=0.42, lowlight=True, vertical=True, invert_x=False,
               invert_y=False, max_yaw=85.0, max_pitch=45.0, port=4242)

def clamp(v, lo, hi): return max(lo, min(hi, v))
def deadzone(v, threshold):
    return math.copysign(max(0., abs(v)-threshold), v)
def packet(yaw, pitch):
    # OpenTrack UDP tracker: X,Y,Z,Yaw,Pitch,Roll, all little-endian doubles.
    return struct.pack('<6d', 0.,0.,0.,float(yaw),float(pitch),0.)

def estimate_pose(face, width, height):
    image = np.array([(face.landmark[i].x*width,face.landmark[i].y*height) for i in POINTS], dtype=np.float64)
    focal = float(width)
    camera = np.array([[focal,0,width/2],[0,focal,height/2],[0,0,1]], dtype=np.float64)
    ok, rvec, _ = cv2.solvePnP(MODEL,image,camera,np.zeros((4,1)),flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok: return None
    rotation,_ = cv2.Rodrigues(rvec)
    angles = cv2.RQDecomp3x3(rotation)[0]
    # OpenCV RQDecomp3x3 angles: pitch(X), yaw(Y), roll(Z) in degrees.
    return np.array([float(angles[1]),float(angles[0])], dtype=np.float64)

class App:
    def __init__(self):
        self.root=tk.Tk(); self.root.title('MaxTrack 0.9.3 — ETS2 / ATS'); self.root.geometry('570x690'); self.root.minsize(520,610)
        self.events=queue.Queue(maxsize=4); self.stop=threading.Event(); self.lock=threading.RLock()
        self.enabled=False; self.raw=None; self.center=None; self.filtered=None; self.last_good=0.; self.fps=0.
        self.status='Iniciando'; self.worker=None; self.scanning=False; self.closing=False; self.scan_results=queue.Queue(); self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try: saved=json.loads(CONFIG.read_text(encoding='utf-8'))
        except (OSError,ValueError): saved={}
        self.settings={**DEFAULT,**{k:v for k,v in saved.items() if k in DEFAULT}}
        self.vars={k:(tk.BooleanVar(value=v) if isinstance(v,bool) else tk.IntVar(value=v) if isinstance(v,int) else tk.DoubleVar(value=v)) for k,v in self.settings.items()}
        self.camera=tk.StringVar(value=str(self.settings['camera']))
        self.info=tk.StringVar(value='Aguardando imagem'); self.mode=tk.StringVar(value='PAUSADO')
        main=ttk.Frame(self.root,padding=14); main.pack(fill='both',expand=True)
        ttk.Label(main,text='MaxTrack 0.9.3',font=('Segoe UI',20,'bold')).pack(anchor='w')
        ttk.Label(main,text='Webcam USB → rastreamento facial → OpenTrack → ETS2 / ATS').pack(anchor='w',pady=(0,10))
        r=ttk.Frame(main);r.pack(fill='x')
        ttk.Label(r,text='Índice da webcam:').pack(side='left')
        self.camera_combo=ttk.Combobox(r,textvariable=self.camera,values=['0'],width=7,state='readonly');self.camera_combo.pack(side='left',padx=8)
        self.camera_combo.bind('<<ComboboxSelected>>', lambda _event: self.restart())
        ttk.Button(r,text='Detectar webcams',command=self.detect_cameras).pack(side='left',padx=3)
        ttk.Button(r,text='Reabrir webcam',command=self.restart).pack(side='left')
        self.preview=tk.Label(main,text='Prévia indisponível',bg='#15191d',fg='white',height=12)
        self.preview.pack(fill='x',pady=10)
        self.preview_image=None
        for label,key,lo,hi in [('Sensibilidade horizontal','sensitivity_x',0.3,5),('Sensibilidade vertical','sensitivity_y',0.3,5),('Zona morta (graus)','deadzone',0,6),('Suavização (mais = menos tremor)','smoothing',0,0.9)]:
            row=ttk.Frame(main);row.pack(fill='x',pady=3)
            ttk.Label(row,text=label).pack(anchor='w')
            ttk.Scale(row,variable=self.vars[key],from_=lo,to=hi,command=lambda _v:self.sync()).pack(fill='x')
        flags=ttk.Frame(main);flags.pack(fill='x',pady=5)
        for i,(label,key) in enumerate([('Melhorar pouca luz','lowlight'),('Rastrear vertical','vertical'),('Inverter horizontal','invert_x'),('Inverter vertical','invert_y')]):
            ttk.Checkbutton(flags,text=label,variable=self.vars[key],command=self.sync).grid(row=i//2,column=i%2,sticky='w',padx=7,pady=3)
        controls=ttk.Frame(main);controls.pack(fill='x',pady=8)
        ttk.Button(controls,text='Ativar / Pausar (F9)',command=self.toggle).pack(side='left',fill='x',expand=True,padx=3)
        ttk.Button(controls,text='Centralizar (F10)',command=self.recenter).pack(side='left',fill='x',expand=True,padx=3)
        ttk.Label(main,textvariable=self.mode,font=('Segoe UI',11,'bold')).pack()
        ttk.Label(main,textvariable=self.info,wraplength=520,justify='center').pack(pady=4)
        ttk.Label(main,text='OpenTrack: Input = UDP over network (porta 4242) | Output = freetrack 2.0 Enhanced\nPressione Start no OpenTrack. O MaxTrack não move o cursor do Windows.',justify='center',wraplength=530).pack(pady=8)
        ttk.Button(main,text='Salvar configurações',command=self.save).pack(fill='x')
        self.listener=keyboard.GlobalHotKeys({'<f9>':lambda:self.root.after(0,self.toggle),'<f10>':lambda:self.root.after(0,self.recenter)})
        try:self.listener.start()
        except Exception as exc:self.status=f'Atalhos indisponíveis: {exc}'
        self.restart();self.root.after(50,self.update_ui);self.root.protocol('WM_DELETE_WINDOW',self.close)

    def sync(self):
        with self.lock:
            for key,var in self.vars.items():self.settings[key]=var.get()

    def save(self):
        self.sync()
        try:CONFIG.write_text(json.dumps(self.settings,indent=2),encoding='utf-8');self.status='Configurações salvas'
        except OSError as exc:messagebox.showerror('Erro ao salvar',str(exc))

    def toggle(self):
        with self.lock:
            self.enabled=not self.enabled; self.filtered=None
            if self.enabled and self.raw is not None and self.center is None:self.center=self.raw.copy()
            active=self.enabled
        if not active:self.send(0.,0.)

    def recenter(self):
        with self.lock:
            if self.raw is not None:self.center=self.raw.copy();self.filtered=None;self.status='Centro atualizado'
            else:self.status='Aguarde o rosto ser detectado'
        self.send(0.,0.)

    def send(self,yaw,pitch):
        try:self.sock.sendto(packet(yaw,pitch),('127.0.0.1',int(self.settings['port'])))
        except (OSError,ValueError):pass

    def detect_cameras(self):
        """Release the current camera before probing; deliver results via the UI queue."""
        if self.scanning:
            return
        self.scanning=True
        self.status='Procurando webcams...'
        self.info.set(self.status)
        self.stop.set()
        def scan():
            if self.worker and self.worker.is_alive():
                self.worker.join(timeout=5)
                if self.worker.is_alive():
                    self.scan_results.put(None)
                    return
            found=[]
            for i in range(6):
                cap=None
                try:
                    cap=cv2.VideoCapture(i,cv2.CAP_DSHOW)
                    if cap.isOpened():
                        ok,frame=cap.read()
                        if ok and frame is not None:
                            found.append(i)
                except Exception:
                    pass
                finally:
                    if cap is not None:
                        cap.release()
            self.scan_results.put(found)
        threading.Thread(target=scan,daemon=True).start()

    def finish_scan(self,found):
        self.scanning=False
        if found is None:
            self.status='A webcam está ocupada. Feche outros aplicativos e tente novamente.'
            self.info.set(self.status)
            self.restart()
            return
        if not found:
            self.camera_combo.configure(values=['0'])
            self.camera.set('0')
            self.status='Nenhuma webcam disponível. Verifique a conexão USB.'
            self.info.set(self.status)
            self.restart()
            return
        self.camera_combo.configure(values=[str(i) for i in found])
        if self.camera.get() not in [str(i) for i in found]:
            self.camera.set(str(found[0]))
        self.status='Webcams encontradas: '+', '.join(map(str,found))
        self.info.set(self.status)
        self.restart()

    def restart(self):
        if self.scanning:return
        if self.worker and self.worker.is_alive():
            self.stop.set();self.worker.join(timeout=2.0)
            if self.worker.is_alive():self.status='Câmera ainda ocupada: tente novamente';return
        try:index=int(self.camera.get())
        except ValueError:index=0
        self.settings['camera']=index
        with self.lock:self.raw=None;self.center=None;self.filtered=None
        self.stop=threading.Event();self.worker=threading.Thread(target=self.track,args=(index,self.stop),daemon=True);self.worker.start()

    def track(self,index,stop):
        cap=cv2.VideoCapture(index,cv2.CAP_DSHOW)
        if not cap.isOpened():self.status=f'Não foi possível abrir a webcam {index}';return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,640);cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
        cap.set(cv2.CAP_PROP_FPS,30);cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
        clahe=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8))
        try:mesh=mp.solutions.face_mesh.FaceMesh(static_image_mode=False,max_num_faces=1,refine_landmarks=False,min_detection_confidence=0.55,min_tracking_confidence=0.55)
        except Exception as exc:self.status=f'Falha ao iniciar MediaPipe: {exc}';cap.release();return
        previous=time.monotonic();last_send=0.; misses=0
        try:
            while not stop.is_set():
                ok,frame=cap.read();now=time.monotonic()
                if not ok:
                    misses+=1;self.status='Sem imagem da webcam'
                    if misses>8:self.send(0.,0.)
                    stop.wait(0.05);continue
                misses=0
                dt=clamp(now-previous,0.001,0.2);previous=now
                self.fps=self.fps*.85+(1/dt)*.15
                frame=cv2.flip(frame,1)
                with self.lock:cfg=self.settings.copy()
                if cfg['lowlight']:
                    yuv=cv2.cvtColor(frame,cv2.COLOR_BGR2YCrCb)
                    yuv[:,:,0]=clahe.apply(yuv[:,:,0]);frame=cv2.cvtColor(yuv,cv2.COLOR_YCrCb2BGR)
                rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB);rgb.flags.writeable=False
                result=mesh.process(rgb)
                h,w=frame.shape[:2];pose=None
                if result.multi_face_landmarks:
                    pose=estimate_pose(result.multi_face_landmarks[0],w,h)
                    for index_id in (1,33,263,61,291):
                        lm=result.multi_face_landmarks[0].landmark[index_id]
                        cv2.circle(frame,(int(lm.x*w),int(lm.y*h)),3,(70,230,90),-1)
                with self.lock:
                    if pose is not None and np.all(np.isfinite(pose)):
                        # Reject impossible single-frame spikes; tolerate intentional fast turns.
                        if self.raw is None or np.max(np.abs(pose-self.raw))<38:
                            self.raw=pose;self.last_good=now
                            if self.center is None:self.center=pose.copy()
                            delta=pose-self.center
                            yaw=deadzone(float(delta[0]),cfg['deadzone'])*cfg['sensitivity_x']
                            pitch=deadzone(float(delta[1]),cfg['deadzone'])*cfg['sensitivity_y'] if cfg['vertical'] else 0.
                            if cfg['invert_x']:yaw=-yaw
                            if cfg['invert_y']:pitch=-pitch
                            target=np.array([clamp(yaw,-cfg['max_yaw'],cfg['max_yaw']),clamp(pitch,-cfg['max_pitch'],cfg['max_pitch'])])
                            if self.filtered is None:self.filtered=target
                            else:
                                # Framerate-independent low-pass with faster response on large changes.
                                tau=0.012+cfg['smoothing']*0.25
                                if np.max(np.abs(target-self.filtered))>12:tau*=0.55
                                alpha=1-math.exp(-dt/max(0.001,tau))
                                self.filtered=self.filtered+(target-self.filtered)*alpha
                    if now-self.last_good>0.65:
                        self.filtered=None;self.raw=None
                    active=self.enabled;out=self.filtered.copy() if self.filtered is not None else None
                if now-last_send>=1/60:
                    self.send(float(out[0]),float(out[1])) if active and out is not None else self.send(0.,0.)
                    last_send=now
                cv2.putText(frame,('ATIVO' if active else 'PAUSADO')+f'  {self.fps:.0f} FPS',(12,26),cv2.FONT_HERSHEY_SIMPLEX,.65,(0,220,90) if active else (0,180,255),2)
                small=cv2.resize(frame,(480,270))
                try:
                    if self.events.full():self.events.get_nowait()
                    self.events.put_nowait((small,pose is not None,out))
                except queue.Empty:pass
        except Exception as exc:self.status=f'Erro de rastreamento: {exc}'
        finally:mesh.close();cap.release();self.send(0.,0.)

    def update_ui(self):
        if self.closing:
            return
        try:
            while True:
                found_cameras=self.scan_results.get_nowait()
                self.finish_scan(found_cameras)
        except queue.Empty:
            pass
        latest=None
        try:
            while True:
                latest=self.events.get_nowait()
        except queue.Empty:
            pass
        if latest is not None:
            frame,found,output=latest
            ok,encoded=cv2.imencode('.png',frame)
            if ok:
                import base64
                self.preview_image=tk.PhotoImage(data=base64.b64encode(encoded.tobytes()).decode('ascii'))
                self.preview.configure(image=self.preview_image,text='',height=270)
            self.info.set(('Rosto detectado' if found else 'Rosto não detectado: aumente a luz') + (f' | Yaw {output[0]:+.1f}° / Pitch {output[1]:+.1f}°' if output is not None else ''))
        with self.lock:
            active=self.enabled
        self.mode.set('RASTREAMENTO ATIVO' if active else 'PAUSADO — saída neutra')
        if any(t in self.status for t in ('Erro','Não foi','Sem imagem','Nenhuma webcam','ocupada','Falha')):
            self.info.set(self.status)
        # The UI polling must continue even while capture is stopped for scanning.
        self.root.after(60,self.update_ui)

    def close(self):
        self.closing=True
        self.save();self.stop.set();self.send(0.,0.)
        try:self.listener.stop()
        except Exception:pass
        try:self.sock.close()
        except OSError:pass
        self.root.destroy()

if __name__=='__main__':App().root.mainloop()
