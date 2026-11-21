# Reference definitions from MaxTrack commit 3d3b978, compared by AST.

def clamp(v, lo, hi): return max(lo, min(hi, v))

def deadzone(v, threshold):
    return math.copysign(max(0., abs(v)-threshold), v)

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
    def toggle(self):
        with self.lock:
            self.enabled=not self.enabled; self.filtered=None
            if self.enabled and self.raw is not None and self.center is None:self.center=self.raw.copy()
            active=self.enabled
        if not active:self.send(0.,0.)
