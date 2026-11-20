"""MaxTrack 0.9: local USB webcam head tracking for OpenTrack UDP input."""
import json, math, os, queue, socket, struct, threading, time, sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import traceback
import cv2
import mediapipe as mp
import numpy as np
from pynput import keyboard
from settings_store import validated, write_settings, PROFILE_KEYS
from stabilization import stabilize, smoothing_alpha, approach_depth, CABIN_SIDE_VIEW, CabinMotion
from interface import build_interface
from windows_tray import WindowsTray

BASE = Path(__file__).resolve().parent
if getattr(sys, 'frozen', False):
    BASE = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MaxTrackPro'
    BASE.mkdir(parents=True, exist_ok=True)
CONFIG = BASE / 'config.json'
POINTS = (1, 152, 33, 263, 61, 291)
MODEL = np.array([(0,0,0),(0,-63.6,-12.5),(-43.3,32.7,-26),(43.3,32.7,-26),(-28.9,-28.9,-24.1),(28.9,-28.9,-24.1)], dtype=np.float64)
DEFAULT = dict(camera=0, camera_fps=30, sensitivity_x=2.4, sensitivity_y=1.0, deadzone=0.8,
               smoothing=0.25, lowlight=False, vertical=True, invert_x=True,
               invert_y=False, max_yaw=105.0, max_pitch=45.0, port=4242, direct_bridge=False, anti_tremor=0.6,
               responsive=True, cabin_mode=False)

def clamp(v, lo, hi): return max(lo, min(hi, v))
def deadzone(v, threshold):
    return math.copysign(max(0., abs(v)-threshold), v)
def packet(yaw, pitch, depth=0., lateral=0.):
    return struct.pack('<6d', float(lateral),0.,float(depth),float(yaw),float(pitch),0.)

def face_span(face, width, height):
    left, right = (face.landmark[i] for i in (33, 263))
    return math.hypot(right.x-left.x, (right.y-left.y)*height/width, right.z-left.z)


def face_height(face, width, height):
    # Vertical face size changes less than eye width when the driver turns sideways.
    forehead, chin = (face.landmark[i] for i in (10, 152))
    return math.hypot((chin.x-forehead.x)*width/height, chin.y-forehead.y)

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

def fallback_pose(face):
    """Estimate approximate head direction from nose vs. eyes and mouth.

    Unlike solvePnP this cannot return physical degrees, but stays responsive
    when the PnP estimate is rejected. Relative center cancels translation.
    """
    lm = face.landmark
    le, re, nose, mouth = (lm[33], lm[263], lm[1], lm[13])
    eye_width = math.hypot(re.x-le.x, re.y-le.y)
    if eye_width < .015:
        return None
    eye_x = (le.x+re.x)*.5
    eye_y = (le.y+re.y)*.5
    yaw = clamp((nose.x-eye_x)/eye_width*90., -65., 65.)
    pitch = clamp(((nose.y-eye_y)/eye_width-.40)*70., -45., 45.)
    return np.array([yaw,pitch], dtype=np.float64)

class App:
    def __init__(self):
        self.root=tk.Tk(); self.root.title('MaxTrack Pro 0.9.21 — ETS2 / ATS'); self.root.geometry('650x840'); self.root.minsize(560,650)
        self.autosave_job=None
        self.in_tray = False
        self.tray = WindowsTray(self.root, self.restore_from_tray, self.close) if sys.platform == 'win32' else None
        style=ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.',background='#17212f',foreground='#e7edf5',font=('Segoe UI',10))
        style.configure('TButton',padding=(10,7),background='#263950')
        style.map('TButton',background=[('active','#355678')])
        style.configure('TEntry',fieldbackground='#243247',foreground='#ffffff')
        style.configure('TCombobox',fieldbackground='#243247',foreground='#ffffff')
        style.map('TCombobox',fieldbackground=[('readonly','#243247')],foreground=[('readonly','#ffffff')])
        style.configure('Horizontal.TProgressbar',background='#46c7b7',troughcolor='#243247')
        self.root.configure(background='#17212f')
        self.events=queue.Queue(maxsize=1); self.stop=threading.Event(); self.lock=threading.RLock()
        self.enabled=True; self.raw=None; self.center=None; self.filtered=None; self.last_good=0.; self.fps=0.
        self.depth_span=None; self.depth_reference=None; self.depth_output=0.
        self.cabin = CabinMotion()
        self.status='Iniciando'; self.worker=None; self.scanning=False; self.closing=False; self.scan_results=queue.Queue(); self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); self.test_until=0.; self.test_start=0.; self.udp_packets=0; self.last_source='aguardando'
        try: saved=json.loads(CONFIG.read_text(encoding='utf-8'))
        except (OSError,ValueError): saved={}
        if not isinstance(saved,dict): saved={}
        self.settings=validated(saved,DEFAULT)
        stored_profiles=saved.get('profiles',{})
        if not isinstance(stored_profiles,dict): stored_profiles={}
        self.profiles={name:{k:v for k,v in validated(stored_profiles.get(name,self.settings),DEFAULT).items() if k in PROFILE_KEYS} for name in ('ETS2','ATS')}
        self.active_profile=saved.get('active_profile','ETS2')
        if self.active_profile not in self.profiles:self.active_profile='ETS2'
        self.profile_name=tk.StringVar(value=self.active_profile)
        # Apply the corrected direction and recommended profile on first launch only.
        if not saved:self.settings.update(DEFAULT)
        if not saved:
            self.settings['profile_097_applied']=True
        self.vars={k:(tk.BooleanVar(value=v) if isinstance(v,bool) else tk.IntVar(value=v) if isinstance(v,int) else tk.DoubleVar(value=v)) for k,v in self.settings.items()}
        self.camera=tk.StringVar(value=str(self.settings['camera']))
        self.info=tk.StringVar(value='Aguardando imagem'); self.mode=tk.StringVar(value='ATIVO')
        self.pose_info=tk.StringVar(value='Pose bruta: aguardando rosto'); self.udp_info=tk.StringVar(value='UDP: aguardando')
        build_interface(self)
        self.listener=keyboard.GlobalHotKeys({'<f9>':lambda:self.root.after(0,self.toggle),'<f10>':lambda:self.root.after(0,self.recenter)})
        try:self.listener.start()
        except Exception as exc:self.status=f'Atalhos indisponíveis: {exc}'
        self.restart();self.ui_job=self.root.after(50,self.update_ui);self.root.protocol('WM_DELETE_WINDOW',self.close)

    def log(self, msg):
        try:
            with (BASE / 'maxtrack_diagnostico.log').open('a', encoding='utf-8') as f:
                f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + str(msg) + '\n')
        except OSError:
            pass

    def apply_responsive_preset(self):
        for key,value in {'smoothing':.25,'anti_tremor':.6,'responsive':True,'lowlight':False}.items():self.vars[key].set(value)
        self.sync()
        self.persist()

    def apply_preset(self):
        preset={'sensitivity_x':DEFAULT['sensitivity_x'],'max_yaw':DEFAULT['max_yaw'],'sensitivity_y':1.0,'deadzone':0.8,
                'smoothing':0.25,'invert_x':True,'invert_y':False,
                'vertical':True,'lowlight':False}
        for key,value in preset.items():self.vars[key].set(value)
        self.sync()
        with self.lock:self.filtered=None
        self.status='Ajustes recomendados aplicados. Olhe para frente e pressione F10.'
        self.save()

    def sync(self):
        with self.lock:
            values=self.settings.copy()
            for key,var in self.vars.items():
                try:values[key]=var.get()
                except (tk.TclError,ValueError):pass
            self.settings=validated(values,DEFAULT)
        if not self.closing:
            if self.autosave_job:self.root.after_cancel(self.autosave_job)
            self.autosave_job=self.root.after(700,self.persist)

    def switch_profile(self,_event=None):
        self.sync()
        self.profiles[self.active_profile]={k:self.settings[k] for k in PROFILE_KEYS}
        self.active_profile=self.profile_name.get()
        for key,value in self.profiles[self.active_profile].items():self.vars[key].set(value)
        self.sync()
        with self.lock:self.filtered=None
        self.persist()

    def persist(self):
        if self.autosave_job:
            self.root.after_cancel(self.autosave_job)
            self.autosave_job=None
        self.profiles[self.active_profile]={k:self.settings[k] for k in PROFILE_KEYS}
        try:
            write_settings(CONFIG,self.settings,self.profiles,self.active_profile)
            self.status='Configurações salvas automaticamente'
        except (OSError,ValueError) as exc:
            self.status='Erro ao salvar configurações'
            self.log(str(exc))

    def save(self):
        self.sync()
        self.persist()

    def toggle(self):
        with self.lock:
            self.enabled=not self.enabled; self.filtered=None
            if self.enabled and self.raw is not None and self.center is None:self.center=self.raw.copy()
            active=self.enabled
        if not active:self.send(0.,0.)

    def recenter(self):
        with self.lock:
            self.depth_reference=self.depth_span; self.depth_output=0.
            if self.raw is not None:
                self.center=self.raw.copy();self.filtered=None;self.status='Centro atualizado'
                self.cabin.recenter()
            else:self.status='Aguarde o rosto ser detectado'
        self.send(0.,0.)

    def send(self,yaw,pitch,depth=0.,lateral=0.):
        with getattr(self,'lock',threading.RLock()):
            previous=getattr(self,'last_sent_pose',(None,None))
            radius=self.settings.get('anti_tremor',0.)
            if yaw==0. and pitch==0.:
                output=(0.,0.)
            else:
                output=(stabilize(yaw,previous[0],radius),stabilize(pitch,previous[1],radius))
            self.last_sent_pose=output
            yaw,pitch=output
        direct=self.settings.get('direct_bridge',False)
        try:self.sock.sendto(packet(yaw,pitch,depth if direct else 0.,lateral if direct else 0.),('127.0.0.1',4243 if direct else int(self.settings['port'])))
        except (OSError,ValueError):pass

    def test_udp(self):
        self.test_start=time.monotonic()
        self.test_until=self.test_start+3.
        self.status = ('Teste ativo por 3 segundos. Observe o giro para os dois lados na cabine.'
                       if self.settings['direct_bridge'] else 'Teste ativo por 3 segundos. Observe o polvo no OpenTrack.')
        self.log('Iniciado teste UDP independente da webcam')

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
        self.vars['camera'].set(index)
        self.sync()
        with self.lock:
            self.raw=None;self.center=None;self.filtered=None
            self.depth_span=None;self.depth_reference=None;self.depth_output=0.
            self.cabin = CabinMotion()
            self.last_good = 0.
        self.stop=threading.Event();self.worker=threading.Thread(target=self.track,args=(index,self.stop),daemon=True);self.worker.start()

    def track(self,index,stop):
        cap=None
        mesh=None
        try:
            self.log(f'Abrindo webcam {index} por DirectShow')
            cap=cv2.VideoCapture(index,cv2.CAP_DSHOW)
            if not cap.isOpened():
                self.log('DirectShow falhou; tentando MSMF')
                cap.release()
                cap=cv2.VideoCapture(index,cv2.CAP_MSMF)
            if not cap.isOpened():
                self.status=f'Não foi possível abrir webcam {index}'
                self.log(self.status)
                return
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
            cap.set(cv2.CAP_PROP_FPS,30)
            self.log('Webcam aberta; iniciando captura independentemente do MediaPipe')
            clahe=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8))
            previous = None
            requested_fps = 30
            misses=0
            last_mesh_try=0.
            mesh_error=''
            last_geometry=None
            aligned_pose=None
            cabin_mode = False
            dark_scene = False
            next_light_check = 0.
            while not stop.is_set():
                with self.lock:
                    cfg = self.settings.copy()
                    if cfg['cabin_mode'] != cabin_mode:
                        cabin_mode = cfg['cabin_mode']
                        self.cabin = CabinMotion()
                        self.filtered = None
                        self.depth_span = self.depth_reference = None
                        self.depth_output = 0.
                fps_limit = cfg['camera_fps']
                if fps_limit != requested_fps:
                    cap.set(cv2.CAP_PROP_FPS, fps_limit)
                    requested_fps = fps_limit
                ok,frame=cap.read()
                if stop.is_set():
                    break
                if not ok or frame is None:
                    misses+=1
                    if misses==1:self.log('Webcam abriu, mas read() falhou')
                    self.status='Sem imagem da webcam'
                    if cabin_mode:
                        with self.lock:
                            elapsed = time.monotonic()-self.last_good
                            if elapsed > .35:
                                self.raw = None
                                aligned_pose = last_geometry = None
                            output = self.cabin.lost(elapsed, .05)
                            active = self.enabled
                        self.send(*output) if active else self.send(0.,0.)
                    elif misses>8:self.send(0.,0.)
                    stop.wait(.05)
                    continue
                if misses:self.log('Captura da webcam recuperada')
                misses=0
                now = time.monotonic()
                if previous is None:
                    elapsed = 1 / fps_limit
                else:
                    # Some driver modes ignore CAP_PROP_FPS. Pace processing in software too.
                    if stop.wait(max(0., previous + 1 / fps_limit - now)):
                        break
                    now = time.monotonic()
                    elapsed = now - previous
                previous = now
                dt = clamp(elapsed, .001, .2)
                self.fps = min(self.fps, fps_limit) * .85 + (1 / elapsed) * .15
                frame=cv2.flip(frame,1)
                if cabin_mode and not cfg['lowlight'] and now >= next_light_check:
                    brightness = cv2.cvtColor(frame[::12, ::12], cv2.COLOR_BGR2GRAY).mean()
                    dark_scene = brightness < (78 if dark_scene else 64)
                    next_light_check = now + .35
                if cfg['lowlight'] or (cabin_mode and dark_scene):
                    yuv=cv2.cvtColor(frame,cv2.COLOR_BGR2YCrCb)
                    yuv[:,:,0]=clahe.apply(yuv[:,:,0])
                    frame=cv2.cvtColor(yuv,cv2.COLOR_YCrCb2BGR)
                pose=None
                span=None
                if mesh is None and (last_mesh_try == 0. or now-last_mesh_try>=5.):
                    last_mesh_try=now
                    try:
                        mesh=mp.solutions.face_mesh.FaceMesh(static_image_mode=False,max_num_faces=1,refine_landmarks=False,min_detection_confidence=.55,min_tracking_confidence=.55)
                        self.log('MediaPipe FaceMesh inicializado - versao '+str(mp.__version__))
                        mesh_error=''
                    except Exception as exc:
                        mesh_error=str(exc)
                        self.log('Falha MediaPipe: '+traceback.format_exc())
                if mesh is not None:
                    try:
                        rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
                        rgb.flags.writeable=False
                        result=mesh.process(rgb)
                        h,w=frame.shape[:2]
                        if result.multi_face_landmarks:
                            face=result.multi_face_landmarks[0]
                            pose=estimate_pose(face,w,h)
                            geometry=fallback_pose(face)
                            if pose is None or not np.all(np.isfinite(pose)) or abs(pose[0])>80 or abs(pose[1])>80:
                                pose=None
                            elif aligned_pose is not None and np.max(np.abs(pose-aligned_pose))>=38:
                                pose=None
                            if pose is None and geometry is not None:
                                if aligned_pose is None:
                                    pose=geometry
                                elif last_geometry is not None:
                                    pose=aligned_pose+np.clip(geometry-last_geometry,-12.,12.)
                                self.last_source='geometria alinhada'
                            elif pose is not None:
                                if self.last_source=='geometria alinhada' and aligned_pose is not None:
                                    predicted=aligned_pose
                                    if geometry is not None and last_geometry is not None:
                                        predicted=aligned_pose+np.clip(geometry-last_geometry,-12.,12.)
                                    correction=pose-predicted
                                    pose=predicted+np.clip(correction,-2.,2.)
                                    if np.max(np.abs(correction))<=2.:
                                        self.last_source='PnP'
                                else:
                                    self.last_source='PnP'
                            if pose is not None:
                                span=face_height(face,w,h) if cabin_mode else face_span(face,w,h)
                                aligned_pose=pose
                                last_geometry=geometry
                            for landmark_id in (1,33,263,61,291):
                                lm=result.multi_face_landmarks[0].landmark[landmark_id]
                                cv2.circle(frame,(int(lm.x*w),int(lm.y*h)),3,(70,230,90),-1)
                    except Exception:
                        self.log('Erro de processamento facial: '+traceback.format_exc())
                        try:mesh.close()
                        except Exception:pass
                        mesh=None
                        mesh_error='Erro de processamento facial (veja log)'
                with self.lock:
                    found = pose is not None and np.all(np.isfinite(pose))
                    if found:
                        if not cabin_mode and span is not None and math.isfinite(span) and span>.015:
                            self.depth_span=span
                            if self.depth_reference is None:self.depth_reference=span
                            depth_target=approach_depth(self.depth_reference,span)
                            self.depth_output+=(depth_target-self.depth_output)*(1-math.exp(-dt/.13))
                        self.raw=pose
                        self.last_good=now
                        if self.center is None:self.center=pose.copy()
                        delta=pose-self.center
                        yaw=deadzone(float(delta[0]),cfg['deadzone'])*cfg['sensitivity_x']
                        pitch=deadzone(float(delta[1]),cfg['deadzone'])*cfg['sensitivity_y'] if cfg['vertical'] else 0.
                        if cfg['invert_x']:yaw=-yaw
                        if cfg['invert_y']:pitch=-pitch
                        pitch = clamp(pitch, -cfg['max_pitch'], cfg['max_pitch'])
                        if cabin_mode:
                            cabin_output = self.cabin.update(yaw, pitch, span, cfg['smoothing'], dt)
                        else:
                            target=np.array([clamp(yaw,-cfg['max_yaw'],cfg['max_yaw']),pitch])
                            if self.filtered is None:self.filtered=target
                            else:
                                alpha=smoothing_alpha(float(np.max(np.abs(target-self.filtered))),dt,cfg['smoothing'],cfg.get('responsive',True))
                                self.filtered=self.filtered+(target-self.filtered)*alpha
                    if now-self.last_good>.35:
                        aligned_pose=None
                        last_geometry=None
                        self.filtered=None
                        self.raw=None
                        self.depth_span=None
                        self.depth_output=0.
                    active=self.enabled
                    if cabin_mode:
                        if not found:
                            cabin_output = self.cabin.lost(now-self.last_good, dt)
                        if not active:
                            self.cabin.output = (0., 0., 0., 0.)
                        out = cabin_output[:2]
                    else:
                        out=self.filtered.copy() if self.filtered is not None else None
                if now < self.test_until:
                    if cfg['direct_bridge']:
                        phase = (now-self.test_start)*math.tau/3.
                        self.send(CABIN_SIDE_VIEW * math.sin(phase)**3, 0.)
                    else:
                        phase=(now-self.test_start)*2*math.pi/1.5
                        self.send(25*math.sin(phase), 10*math.cos(phase))
                elif active and cabin_mode:self.send(*cabin_output)
                elif active and out is not None:self.send(float(out[0]),float(out[1]),self.depth_output)
                else:self.send(0.,0.)
                self.udp_packets+=1
                if self.in_tray:
                    continue
                cv2.putText(frame,('ATIVO' if active else 'PAUSADO')+f' {self.fps:.0f} FPS',(12,26),cv2.FONT_HERSHEY_SIMPLEX,.65,(0,220,90) if active else (0,180,255),2)
                if mesh_error:
                    cv2.putText(frame,'CAMERA OK - MEDIAPIPE COM ERRO',(8,55),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,80,255),1)
                small=cv2.resize(frame,(480,360))
                try:
                    if self.events.full():self.events.get_nowait()
                    self.events.put_nowait((small,pose.copy() if pose is not None else None,out,mesh_error))
                except queue.Empty:pass
        except Exception:
            self.status='Erro de captura (veja maxtrack_diagnostico.log)'
            self.log(traceback.format_exc())
        finally:
            if mesh is not None:
                try:mesh.close()
                except Exception:pass
            if cap is not None:cap.release()
            self.send(0.,0.)
            self.log('Webcam liberada')

    def minimize_to_tray(self):
        if not self.tray.show():
            self.root.iconify()
            return
        self.in_tray = True
        self.preview.configure(image='')
        self.preview_image = None
        self.root.withdraw()

    def restore_from_tray(self):
        if self.closing:
            return
        self.in_tray = False
        self.root.deiconify()
        self.root.lift()
        self.tray.hide()

    def update_ui(self):
        self.ui_job = None
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
        if self.in_tray:
            self.ui_job = self.root.after(250, self.update_ui)
            return
        if latest is not None:
            frame,pose,output,mesh_error=latest
            found=pose is not None
            self.pose_info.set((f'Pose bruta ({self.last_source}): Yaw {pose[0]:+.2f} / Pitch {pose[1]:+.2f}' if found else 'Pose bruta: sem rosto detectado') + (' | ERRO MEDIAPIPE: '+str(mesh_error)[:120] if mesh_error else ''))
            try:
                rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
                self.preview_image=ImageTk.PhotoImage(Image.fromarray(rgb))
                self.preview.configure(image=self.preview_image,text='',height=360)
            except Exception:
                self.log('Erro ao mostrar prévia: '+traceback.format_exc())
            self.info.set(('Rosto detectado' if found else ('Webcam OK | Erro MediaPipe (veja log)' if mesh_error else 'Webcam OK | Procurando rosto')) + (f' | Yaw {output[0]:+.1f}° / Pitch {output[1]:+.1f}°' if output is not None else ''))
        with self.lock:
            active=self.enabled
        self.fps_info.set(f'CAPTURA  {self.fps:.0f} FPS')
        self.mode.set('RASTREAMENTO ATIVO' if active else 'PAUSADO — saída neutra')
        self.udp_info.set(('Saída: ponte SCS experimental • UDP 4243' if self.settings.get('direct_bridge') else 'Saída: compatibilidade OpenTrack • UDP '+str(self.settings['port']))+' | '+self.status)
        if latest is None and any(t in self.status for t in ('Erro','Não foi','Sem imagem','Nenhuma webcam','ocupada','Falha')):
            self.info.set(self.status)
        # The UI polling must continue even while capture is stopped for scanning.
        self.ui_job = self.root.after(60,self.update_ui)

    def close(self):
        if self.closing:
            return
        self.closing=True
        if self.ui_job is not None:
            self.root.after_cancel(self.ui_job)
            self.ui_job = None
        if self.tray is not None:
            self.tray.close()
        self.save();self.stop.set();self.send(0.,0.)
        if self.worker and self.worker.is_alive():
            self.root.after(100,self.finish_close)
            return
        self.finish_close()

    def finish_close(self):
        if self.worker and self.worker.is_alive():
            self.root.after(100,self.finish_close)
            return
        try:self.listener.stop()
        except Exception:pass
        try:self.sock.close()
        except OSError:pass
        self.root.destroy()

def package_self_test(destination):
    """Exercise bundled native libraries/models without webcam or global hotkeys."""
    root=tk.Tk()
    root.withdraw()
    try:
        root.update()
        with mp.solutions.face_mesh.FaceMesh(static_image_mode=True,max_num_faces=1) as mesh:
            result=mesh.process(np.zeros((480,640,3),dtype=np.uint8))
            assert not result.multi_face_landmarks
        Path(destination).write_text(json.dumps({'status':'passed','numpy':np.__version__,
            'mediapipe':mp.__version__,'opencv':cv2.__version__,
            'scope':'Tk, native imports, FaceMesh bundled models; no webcam/game test'},indent=2),encoding='utf-8')
    finally:root.destroy()

def start_tracker():
    from max_store import Licenses, StoreError, release_config

    try:
        config = release_config()
        directory = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MaxHub'
        if config and not Licenses(config, directory).allows('track'):
            raise StoreError('Abra o Max Hub e ative o MaxTrack Pro com a chave da sua conta.')
    except StoreError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo('MaxTrack Pro', str(exc), parent=root)
        root.destroy()
        return

    app = App()
    if config:
        def check_license():
            if not app.closing:
                if Licenses(config, directory).allows('track'):
                    app.root.after(60_000, check_license)
                else:
                    app.close()

        app.root.after(60_000, check_license)
    app.root.mainloop()


if __name__=='__main__':
    if len(sys.argv)==7 and sys.argv[1]=='--configure-ets2':
        from ets2_install import run_setup
        sys.exit(run_setup(*(Path(arg) for arg in sys.argv[2:])))
    elif len(sys.argv)==3 and sys.argv[1]=='--self-test':package_self_test(sys.argv[2])
    else:start_tracker()
