"""
Rigify animators as a module, so the film builder can drive a Rigify-fitted character
the way it drives the kit rig. Same motion as rigify_walk.py (IK ground contacts, hips
that vault and sway, arms brought to hanging with a lateral elbow hinge), wrapped in a
class that owns one rig.

    actor = RigifyActor(rig, char, fps=16)
    actor.walk(f0, f1, path_fn)            # path_fn(t in 0..1) -> (x, y, z, heading), kit convention
    actor.idle(f0, f1, (x, y, z), heading, gestures=[(fa, fb, kind)], look_at_fn=None)

Kit heading convention: heading 0 faces +Y. This rig faces -Y at yaw 0, so yaw = heading + pi.
"""
import math, os
import bpy, mathutils


class RigifyActor:
    def __init__(self, rig, char, fps=16):
        self.rig, self.char, self.fps = rig, char, fps
        self.pb = rig.pose.bones
        zs = [(char.matrix_world @ v.co).z for v in char.data.vertices]
        self.H = max(zs) - min(zs)
        H = self.H
        self.STRIDE = float(os.environ.get("RW_STRIDE", "0.56")) * H
        self.LIFT = float(os.environ.get("RW_LIFT", "0.045")) * H
        self.DROP = float(os.environ.get("RW_DROP", "0.062")) * H
        self.PALM = float(os.environ.get("RW_PALM", "-70"))
        self._roll = {}
        self.sc = bpy.context.scene

    # ---------------------------------------------------------------- helpers
    def rest(self, name):
        return self.rig.data.bones[name].head_local.copy()

    def key_loc(self, name, rig_space, f):
        b = self.pb[name]
        b.location = self.rig.data.bones[name].matrix_local.inverted() @ rig_space
        b.keyframe_insert("location", frame=f)

    def key_rot(self, name, eul, f):
        b = self.pb[name]
        b.rotation_mode = 'XYZ'; b.rotation_euler = eul
        b.keyframe_insert("rotation_euler", frame=f)

    def switches(self, f):
        """IK/FK and stretch are driver-read custom properties: key them, then re-tag."""
        pb, rig, sc = self.pb, self.rig, self.sc
        for side in ("L", "R"):
            for bone, props in (("thigh_parent." + side, {"IK_FK": 0.0, "IK_Stretch": 0.0}),
                                ("upper_arm_parent." + side, {"IK_FK": 1.0, "IK_Stretch": 0.0})):
                for k, v in props.items():
                    if k in pb[bone].keys():
                        pb[bone][k] = v
                        pb[bone].keyframe_insert('["%s"]' % k, frame=f)
        rig.update_tag(); sc.frame_set(f + 1); sc.frame_set(f); bpy.context.view_layer.update()

    def reset_pose(self):
        for b in self.pb:
            b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, 0); b.location = (0, 0, 0)

    def arm_pose(self, side, fwd, f, out_deg=10.0):
        pb, rig = self.pb, self.rig
        name = "upper_arm_fk." + side
        R = rig.data.bones[name].matrix_local.to_3x3()
        d = (R @ mathutils.Vector((0, 1, 0))).normalized()
        sgn = 1 if d.x >= 0 else -1
        out = math.radians(out_deg)
        y_axis = mathutils.Vector((sgn * math.sin(out), 0.0, -math.cos(out))).normalized()

        def frame_for(xsign):
            x_axis = mathutils.Vector((xsign, 0.0, 0.0))
            x_axis = (x_axis - y_axis * x_axis.dot(y_axis)).normalized()
            z_axis = x_axis.cross(y_axis).normalized()
            T = mathutils.Matrix((x_axis, y_axis, z_axis)).transposed()
            return T @ R.inverted()

        if side not in self._roll:
            best, best_score = 1.0, None
            fk = pb["forearm_fk." + side]
            saved = (pb[name].rotation_mode, pb[name].rotation_quaternion.copy(), fk.rotation_mode, fk.rotation_euler.copy())
            for xsign in (1.0, -1.0):
                pb[name].rotation_mode = 'QUATERNION'
                pb[name].rotation_quaternion = (R.inverted() @ frame_for(xsign) @ R).to_quaternion()
                fk.rotation_mode = 'XYZ'; fk.rotation_euler = (math.radians(40), 0, 0)
                bpy.context.view_layer.update()
                ua = (rig.matrix_world @ pb["DEF-upper_arm." + side].matrix).to_3x3() @ mathutils.Vector((0, 1, 0))
                fa = (rig.matrix_world @ pb["DEF-forearm." + side].matrix).to_3x3() @ mathutils.Vector((0, 1, 0))
                fold = fa - ua * fa.dot(ua)
                # forward in the RIG's frame (it faces -Y): undo the object yaw
                fold = rig.matrix_world.to_3x3().inverted() @ fold
                score = -fold.normalized().y if fold.length > 1e-6 else -1
                if best_score is None or score > best_score:
                    best, best_score = xsign, score
            pb[name].rotation_mode, pb[name].rotation_quaternion = saved[0], saved[1]
            fk.rotation_mode, fk.rotation_euler = saved[2], saved[3]
            self._roll[side] = best
        Rw = frame_for(self._roll[side])
        q = mathutils.Quaternion((1, 0, 0), fwd).to_matrix() @ Rw
        b = pb[name]
        b.rotation_mode = 'QUATERNION'
        b.rotation_quaternion = (R.inverted() @ q @ R).to_quaternion()
        b.keyframe_insert("rotation_quaternion", frame=f)

    # ---------------------------------------------------------------- walk
    def walk(self, f0, f1, path_fn, stride_hz=None):
        """path_fn(t in 0..1) -> (x, y, z, heading) in the kit's convention."""
        rig, pb, sc, H, FPS = self.rig, self.pb, self.sc, self.H, self.fps
        STRIDE, LIFT, DROP = self.STRIDE, self.LIFT, self.DROP
        self.reset_pose(); self.switches(f0)
        n = max(1, f1 - f0)
        # path length -> speed -> cycle time
        pts = [path_fn(i / 60.0) for i in range(61)]
        length = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(60))
        dur = n / FPS
        speed = max(1e-4, length / dur)
        cycle = STRIDE / speed
        foot_rest = {s: self.rest("foot_ik." + s) for s in ("L", "R")}
        hip_mid = (self.rest("DEF-thigh.L") + self.rest("DEF-thigh.R")) / 2
        hip_off = mathutils.Vector((hip_mid.x, hip_mid.y, 0))

        def at(t):
            x, y, z, h = path_fn(min(1.0, max(0.0, t)))
            return x, y, z, h + math.pi

        for f in range(f0, f1 + 1):
            t = (f - f0) / n
            x, y, z, yaw = at(t)
            ph = ((t * dur) / cycle) % 1.0
            fwd = mathutils.Vector((math.sin(yaw), -math.cos(yaw), 0))
            side = mathutils.Vector((math.cos(yaw), math.sin(yaw), 0))
            bob = -DROP + 0.022 * H * abs(math.sin(2 * math.pi * ph))
            rig.location = (x, y, z + bob); rig.rotation_mode = 'XYZ'; rig.rotation_euler = (0, 0, yaw)
            rig.keyframe_insert("location", frame=f); rig.keyframe_insert("rotation_euler", frame=f)
            self.key_rot("torso", (math.radians(4), 0, 0), f)
            sway = math.sin(2 * math.pi * ph)
            pb["torso"].location = (0.022 * H * sway, 0, 0); pb["torso"].keyframe_insert("location", frame=f)
            self.key_rot("hips", (0, math.radians(5) * sway, math.radians(-8) * sway), f)
            self.key_rot("chest", (0, 0, math.radians(5) * sway), f)
            self.key_rot("head", (0, 0, math.radians(-2) * sway), f)
            for s, off in (("L", 0.0), ("R", 0.5)):
                pl = (ph + off) % 1.0
                k = math.floor(((t * dur) / cycle) + off)

                def contact(idx):
                    tt = (idx - off) * cycle
                    cx, cy, cz, cyaw = at(max(0.0, tt) / dur)
                    fw = mathutils.Vector((math.sin(cyaw), -math.cos(cyaw), 0))
                    sd = mathutils.Vector((math.cos(cyaw), math.sin(cyaw), 0))
                    lat = foot_rest[s].x - hip_mid.x
                    hoff = mathutils.Matrix.Rotation(cyaw, 3, 'Z') @ hip_off
                    return mathutils.Vector((cx, cy, cz)) + hoff + fw * (STRIDE * 0.25) + sd * lat

                if pl < 0.5:
                    pos = contact(k); pos.z += foot_rest[s].z
                else:
                    u = (pl - 0.5) / 0.5; ue = u * u * (3 - 2 * u)
                    p0, p1 = contact(k), contact(k + 1)
                    pos = p0.lerp(p1, ue); pos.z += foot_rest[s].z + LIFT * math.sin(math.pi * u)
                Mw = mathutils.Matrix.Translation((x, y, z + bob)) @ mathutils.Matrix.Rotation(yaw, 4, 'Z')
                self.key_loc("foot_ik." + s, Mw.inverted() @ pos, f)
                roll = 0.0
                if pl < 0.12:
                    roll = math.radians(-14) * (1 - pl / 0.12)
                elif 0.38 < pl < 0.5:
                    roll = math.radians(22) * ((pl - 0.38) / 0.12)
                self.key_rot("foot_ik." + s, (roll, 0, 0), f)
            for s, sg in (("L", 1), ("R", -1)):
                sw = math.sin(2 * math.pi * ph) * sg
                self.arm_pose(s, math.radians(24) * sw, f)
                self.key_rot("forearm_fk." + s, (math.radians(28 + 16 * max(0.0, sw)), 0, 0), f)
                self.key_rot("hand_fk." + s, (0, math.radians(self.PALM) * sg, 0), f)

    # ---------------------------------------------------------------- idle
    GESTURES = {
        "nod": lambda u: dict(head_x=0.14 * math.sin(u * math.pi * 2) * math.sin(u * math.pi)),
        "shake": lambda u: dict(head_z=0.10 * math.sin(u * math.pi * 3) * math.sin(u * math.pi)),
        "hand_raise": lambda u: dict(raise_=math.sin(u * math.pi) ** 0.7),
        "look_away": lambda u: dict(head_z=-0.38 * math.sin(u * math.pi), head_x=0.03 * math.sin(u * math.pi)),
        "lean_in": lambda u: dict(chest_x=0.10 * math.sin(u * math.pi), head_x=0.04 * math.sin(u * math.pi)),
        "weight_shift": lambda u: dict(hips_y=0.12 * math.sin(u * math.pi), chest_z=0.05 * math.sin(u * math.pi)),
    }

    def idle(self, f0, f1, pos, heading, gestures=None, look_at_fn=None):
        rig, pb, sc, H, FPS = self.rig, self.pb, self.sc, self.H, self.fps
        self.reset_pose(); self.switches(f0)
        yaw = heading + math.pi
        gestures = gestures or []
        hang = None
        chest = self.rest("chest")
        up = mathutils.Vector((chest.x - 0.06 * H, chest.y - 0.13 * H, chest.z + 0.02 * H))
        par = pb["upper_arm_parent.R"]
        for f in range(f0, f1 + 1):
            t = (f - f0) / FPS
            tb = 2 * math.pi * 0.22 * t; ts = 2 * math.pi * 0.07 * t
            g = dict(head_x=0.0, head_z=0.0, chest_x=0.0, chest_z=0.0, hips_y=0.0, raise_=0.0)
            for (fa, fb, kind) in gestures:
                if fa <= f <= fb and kind in self.GESTURES:
                    u = (f - fa) / max(1, fb - fa)
                    for k, v in self.GESTURES[kind](u).items():
                        g[k] += v
            rig.location = (pos[0], pos[1], pos[2] - 0.25 * self.DROP); rig.rotation_mode = 'XYZ'; rig.rotation_euler = (0, 0, yaw)
            rig.keyframe_insert("location", frame=f); rig.keyframe_insert("rotation_euler", frame=f)
            self.key_rot("chest", (0.03 * math.sin(tb) + g["chest_x"], 0, 0.02 * math.sin(ts) + g["chest_z"]), f)
            pb["hips"].location = (0.012 * H * math.sin(ts), 0, -0.004 * H * abs(math.sin(ts))); pb["hips"].keyframe_insert("location", frame=f)
            self.key_rot("hips", (0, g["hips_y"], -0.04 * math.sin(ts)), f)
            look = 0.0
            if look_at_fn is not None:
                tx, ty = look_at_fn(f)
                target_heading = math.pi + math.atan2(-(tx - pos[0]), ty - pos[1])
                look = target_heading - heading
                look = math.atan2(math.sin(look), math.cos(look))
                look = max(-0.35, min(0.35, look))
            self.key_rot("head", (0.02 * math.sin(tb) + g["head_x"], 0.03 * math.sin(ts * 1.3), 0.7 * look + g["head_z"]), f)
            self.key_rot("neck", (0.3 * g["head_x"], 0, 0.3 * look), f)
            for s, sg in (("L", 1), ("R", -1)):
                self.arm_pose(s, 0.02 * math.sin(tb + sg), f)
                self.key_rot("forearm_fk." + s, (math.radians(24 + 3 * math.sin(tb)), 0, 0), f)
                self.key_rot("hand_fk." + s, (0, math.radians(self.PALM) * sg, 0), f)
            # hand raise: blend the right arm to IK while the gesture is live
            r = g["raise_"]
            if hang is None:
                sc.frame_set(f0); hang = (rig.matrix_world.inverted() @ (rig.matrix_world @ pb["DEF-hand.R"].head)).copy()
                hang = pb["DEF-hand.R"].head.copy()
            ikfk = 1.0 - min(1.0, r * 4.0)
            par["IK_FK"] = ikfk; par.keyframe_insert('["IK_FK"]', frame=f)
            self.key_loc("hand_ik.R", hang.lerp(up, r), f)
            self.key_rot("hand_ik.R", (math.radians(-40) * r, 0, math.radians(30) * r), f)
        rig.update_tag(); sc.frame_set(f0 + 1); sc.frame_set(f0)

    # ---------------------------------------------------------------- talk
    def talk(self, f0, envelope, jaw_deg=22.0):
        """Jaw open from an envelope (0..1 per frame), on jaw_master if the rig has one."""
        if "jaw_master" not in self.pb:
            return
        for i, a in enumerate(envelope):
            self.key_rot("jaw_master", (math.radians(jaw_deg) * float(a), 0, 0), f0 + i)
