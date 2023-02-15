import bpy
import numpy as np
import os
import datetime
import rowan as rw
import yaml
from rclpy.node import Node
from ..sim_data_types import State, Action

# rotation vectors are axis-angle format in "compact form", where
# theta = norm(rvec) and axis = rvec / theta
# they can be converted to a matrix using cv2. Rodrigues, see
# https://docs.opencv.org/4.7.0/d9/d0c/group__calib3d.html#ga61585db663d9da06b68e70cfbf6a1eac
def opencv2quat(rvec):
    angle = np.linalg.norm(rvec)
    if angle == 0:
        q = np.array([1,0,0,0])
    else:
        axis = rvec.flatten() / angle
        q = rw.from_axis_angle(axis, angle)
    return q

class Visualization:

    def __init__(self, node: Node, params: dict, names: list[str], states: list[State]):
        self.node = node

        ### # internal rotation to ensure that Z<0 is in front, X>0 is right, and Y>0 is up
        ### # so that blender takes picture from cf's perspective, where X>0 is front, Y>0 is left, and Z>0 is up
        ### self._rot_world_2_cam = np.array([
        ###     [ 0, 0,-1],
        ###     [-1, 0, 0],
        ###     [ 0, 1, 0],
        ### ])

        # internal rotation to ensure that objects are in front of the camera as planned
        self._rot_cam_2_world = np.array([
            [ 0,-1, 0],
            [ 0, 0, 1],
            [-1, 0, 0],
        ])

        ## blender 
        # load environment
        world = bpy.context.scene.world
        world.use_nodes = True
        env = world.node_tree.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load("src/crazyswarm2/crazyflie_sim/data/env.hdr")
        node_tree = world.node_tree
        node_tree.links.new(env.outputs["Color"], node_tree.nodes["Background"].inputs["Color"])

        # import crazyflie object 
        bpy.ops.import_scene.obj(filepath="src/crazyswarm2/crazyflie_sim/data/cf.obj", axis_forward="Y", axis_up="Z")
        self.cf_default = bpy.data.objects["cf"]
        # save scene
        self.scene = bpy.context.scene
        self.scene.render.resolution_x = 320
        self.scene.render.resolution_y = 320
        self.scene.render.pixel_aspect_x = 1.0
        self.scene.render.pixel_aspect_y = 1.0
        self.scene.render.image_settings.file_format = "JPEG"
        self.scene.unit_settings.length_unit = "METERS"
        self.scene.unit_settings.system = "METRIC"
        self.scene.unit_settings.scale_length = 1.0
        #self.scene.render.threads = 2  # max CPU cores to use to render

        # remove default objects
        bpy.data.objects.remove(bpy.data.objects["Cube"])
        bpy.data.objects.remove(bpy.data.objects["Light"])
        # create lamp
        lamp_data = bpy.data.lights.new(name="Lamp", type="SUN")
        lamp_data.energy = 1.5
        lamp_data.angle = 0.19198621809482574  # 11 deg
        self.lamp = bpy.data.objects.new(name="Lamp", object_data=lamp_data)
        bpy.context.collection.objects.link(self.lamp)
        bpy.context.view_layer.objects.active = self.lamp
        # camera
        self.camera = bpy.data.objects["Camera"]
        self.camera.data.lens = 0.7376461029052734
        self.camera.data.lens_unit = "FOV"
        self.camera.data.sensor_fit = "AUTO"
        self.camera.data.sensor_width = 1.4
        self.camera.data.sensor_height = 18
        self.camera.data.angle = 1.518436431884765  # 87 deg
        self.camera.data.clip_start = 1.1e-6
        # link camera to scene


        self.cf_default.hide_render = False
        # set rotation mode to quaternion
        self.cf_default.rotation_mode = "QUATERNION"
        self.camera.rotation_mode = "QUATERNION"
        self.lamp.rotation_mode = "QUATERNION"

        base = "simulation_results"  
        self.path = base + "/" + datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S") + "/Raw-Dataset"
        os.makedirs(self.path, exist_ok=True) 

        self.ts = []
        self.frame = 0
        self.interval = params["interval"]  # number of frames/time steps between renders

        self.names = names
        self.n = len(names)
        self.state_filenames = []
        self.cam_state_filenames = []

        # dictionary with (name, idx) pairs to later find corresponding cf
        self.names_idx_map = dict()
        # init list
        self.cf_list = [self.cf_default]
        self.cf_cameras = params["cf_cameras"] if "cf_cameras" in params else dict()
        # matrix where rows are the constant transformation between camera and its cf
        # it should only be accessed if corresponding cf carries a camera
        self.Q_virt_cf_cam = np.zeros((self.n, 4))
        

        for idx, (name, state) in enumerate(zip(names, states)):
            self.names_idx_map[name] = idx
            if idx > 0:
                # cf copies
                cf_copy = self.cf_default.copy()
                bpy.context.collection.objects.link(cf_copy)
                self.cf_list.append(cf_copy)
            # set rotations
            self.cf_list[idx].rotation_quaternion = np.array(state.quat)
            # set positions
            self.cf_list[idx].location = np.array(state.pos)

        # setup fixed observer camera if enabled
        self.observer_cam = False
        if "observer" in params and params["observer"]["enabled"]:
            self.observer_cam = True
            self.p_fixed_obs_cam = np.array(params["observer"]["pos"])
            self.q_fixed_obs_cam = np.array(params["observer"]["quat"])
            os.mkdir(self.path + "/cam/")  # create dir camera to save images in (cfs have their own as well)
            self.cam_sf = f"{self.path}/cam/cam.csv"
            # calibration
            calibration_sf = f"{self.path}/cam/calibration.yaml"
            calibration = params["observer"]["calibration"]
            calibration["tvec"] = np.zeros(3).tolist()
            calibration["dist_coeff"] = np.zeros(5).tolist()
            calibration["camera_matrix"] = np.array([[170.0,0,160.0], [0,170.0,160.0],[0,0,1]]).tolist()
            with open(calibration_sf, "w") as file:
                yaml.dump(calibration, file)
            rvec = np.array(calibration["rvec"])
            q_real_camera_to_robot = rw.inverse(opencv2quat(rvec))
            q_virtual_camera_to_real_camera = rw.from_euler(np.pi, 0, 0, "xyz")
            self.q_virt_obs_cam = rw.multiply(q_real_camera_to_robot, q_virtual_camera_to_real_camera)
            with open(self.cam_sf, "w") as file:
                file.write("image_name,timestamp,x,y,z,qw,qx,qy,qz\n")

        for name in names:
            os.mkdir(self.path + "/" + name + "/")  # create dir for every cf for saving images
            csf = f"{self.path}/{name}/{name}.csv"
            calibration_sf = f"{self.path}/{name}/calibration.yaml"
            # initialize <robot_name>/<robot_name>.csv
            self.state_filenames.append(csf)
            ### self.cam_state_filenames.append(cam_sf)
            with open(csf, "w") as file:
                file.write("image_name,timestamp,x,y,z,qw,qx,qy,qz\n")
            if name in self.cf_cameras:
                calibration = self.cf_cameras[name]["calibration"]
                calibration["tvec"] = np.zeros(3).tolist()
                calibration["dist_coeff"] = np.zeros(5).tolist()
                calibration["camera_matrix"] = np.array([[170.0,0,160.0], [0,170.0,160.0],[0,0,1]]).tolist()
                with open(calibration_sf, "w") as file:
                    yaml.dump(calibration, file)
                rvec = np.array(calibration["rvec"])
                q_real_camera_to_robot = rw.inverse(opencv2quat(rvec))
                q_virtual_camera_to_real_camera = rw.from_euler(np.pi, 0, 0, "xyz")
                self.Q_virt_cf_cam[self.names_idx_map[name]] = rw.multiply(q_real_camera_to_robot, q_virtual_camera_to_real_camera)


    def step(self, t, states: list[State], states_desired: list[State], actions: list[Action]):
        # only render and record every `self.interval`th frame:
        if self.frame % self.interval == 0: 
            # quaternion matrix
            Q = np.zeros((self.n, 4))  
            # position matrix
            P = np.zeros((self.n, 3))

            # first put everything in place and record cfs's states
            for name, state in zip(self.names, states):
                idx = self.names_idx_map[name]
                Q[idx] = np.array(state.quat)
                P[idx] = np.array(state.pos) 

                # set rotations
                self.cf_list[idx].rotation_quaternion = Q[idx]
                # set positions
                self.cf_list[idx].location = P[idx]
                # record states 
                image_name = f"{self.names[idx]}_{self.frame//self.interval:05}.jpg" if name in self.cf_cameras else "None" # image capturing scene from cf's pov or None
                # record cf's state in world frame
                with open(self.state_filenames[idx], "a") as file:
                    file.write(f"{image_name},{t},{P[idx,0]},{P[idx,1]},{P[idx,2]},{Q[idx,0]},{Q[idx,1]},{Q[idx,2]},{Q[idx,3]}\n")

            if self.observer_cam:
                # take picture from fixed observer camera's pov
                # rotation
                q_cam = rw.multiply(self.q_fixed_obs_cam, self.q_virt_obs_cam)
                self.camera.rotation_quaternion = q_cam
                self.lamp.rotation_quaternion = q_cam
                # positions
                p_cam = self.p_fixed_obs_cam
                self.camera.location = p_cam
                self.lamp.location = p_cam
                image_name = f"cam_{self.frame//self.interval:05}.jpg"  # image capturing scene from cf's pov
                # record observer camera state in world frame if enabled
                with open(self.cam_sf, "a") as file:
                    file.write(f"{image_name},{t},{self.p_fixed_obs_cam[0]},{self.p_fixed_obs_cam[1]},{self.p_fixed_obs_cam[2]},{self.q_fixed_obs_cam[0]},{self.q_fixed_obs_cam[1]},{self.q_fixed_obs_cam[2]},{self.q_fixed_obs_cam[3]}\n")
                # Render image
                self.scene.render.filepath = f"{self.path}/cam/{image_name}"
                bpy.ops.render.render(write_still=True)

            # render images from cfs' perspectives
            for name, state in zip(self.names, states):
                idx = self.names_idx_map[name]
                if name not in self.cf_cameras:
                    continue
                # rotation
                self.camera.rotation_quaternion = rw.multiply(Q[idx], self.Q_virt_cf_cam[idx])
                self.lamp.rotation_quaternion = self.camera.rotation_quaternion
                # positions
                p_cam = P[idx] ### + rw.to_matrix(Q[idx]) @ np.array([0.025, 0.0, 0.01])  # uncomment in case cf's camera has a constant offset wrt its cf
                self.camera.location = p_cam
                self.lamp.location = p_cam
                # hide corresponding cf for rendering
                self.cf_list[idx].hide_render = True
                # Render image
                image_name = f"{name}_{self.frame//self.interval:05}.jpg"  # image capturing scene from cf's pov
                self.scene.render.filepath = f"{self.path}/{name}/{image_name}"
                bpy.ops.render.render(write_still=True)
                # show again after rendering
                self.cf_list[idx].hide_render = False

            self.ts.append(t)
        self.frame += 1

    def shutdown(self):
        for idx in range(1,self.n):
            bpy.data.objects.remove(self.cf_list[idx])
