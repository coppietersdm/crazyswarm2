import unittest

from pathlib import Path
import shutil
import os
from plotter_class import Plotter
from mcap_handler import McapHandler
from subprocess import Popen, PIPE, TimeoutExpired
import time
import signal
import atexit

#############################

def setUpModule():

    path = Path(__file__)           #Path(__file__) in this case "/home/github/actions-runner/_work/crazyswarm2/crazyswarm2/ros2_ws/src/crazyswarm2/systemtests/test_flights.py" ; path.parents[0]=.../systemstests
    
    #delete results, logs and bags of previous experiments if they exist
    if(Path(path.parents[3] / "results").exists()):
        shutil.rmtree(path.parents[3] / "results")  

    os.makedirs(path.parents[3] / "results")  # /home/github/actions-runner/_work/crazyswarm2/crazyswarm2/ros2_ws/results

def tearDownModule():
    pass


def clean_process(process:Popen) -> int :
    '''Kills process and its children on exit if they aren't already terminated (called with atexit). Returns 0 on termination, 1 if SIGKILL was needed''' 
    if process.poll() == None:
        group_id = os.getpgid(process.pid)
        print(f"cleaning process {group_id}")
        os.killpg(group_id, signal.SIGTERM)
        time.sleep(0.01) #necessary delay before first poll
        i=0
        while i < 10 and process.poll() == None:  #in case the process termination is lazy and takes some time, we wait up to 0.5 sec per process
            if process.poll() != None:
                return 0  #if we have a returncode-> it terminated
            time.sleep(0.05) #if not wait a bit longer
        if(i == 9):
            os.killpg(group_id, signal.SIGKILL)
            return 1  #after 0.5s we stop waiting, consider it did not terminate correctly and kill it
        return 0
    else:
        return 0 #process already terminated


class TestFlights(unittest.TestCase):

    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.test_file = None
        self.launch_crazyswarm : Popen = None 
        self.ros2_ws = Path(__file__).parents[3] # path to ros2 workspace (in this case /home/github/actions-runner/_work/crazyswarm2/crazyswarm2/ros2_ws )
        self.src = f"source {str(self.ros2_ws)}/install/setup.bash"   # command line to source crazyflie custom commands for crazyflie
        self.folder_name = None #name of the folder where a test will be saved

    def idFolderName(self):
        return self.id().split(".")[-1] #returns the name of the test_function currently being run, for example "test_figure8"

    # runs once per test_ function
    def setUp(self):

        if(Path(Path.home() / ".ros/log").exists()): #delete log files of the previous test
            shutil.rmtree(Path.home() / ".ros/log")
        self.test_file = None

        # launch server
        command = f"{self.src} && ros2 launch crazyflie launch.py"
        self.launch_crazyswarm = Popen(command, shell=True, stderr=True, stdout=PIPE, text=True,
                                start_new_session=True, executable="/bin/bash")
        atexit.register(clean_process, self.launch_crazyswarm)  #atexit helps us to make sure processes are cleaned even if script exits unexpectedly

        #enable logging
        # try:
        #     command = "python3 set_parameter.py usd.logging 1"
        #     set_logging = Popen(command, shell=True, stderr=True, stdout=PIPE, text=True,
        #                         cwd=self.ros2_ws/"src/crazyswarm2/systemtests", start_new_session=True, executable="/bin/bash")
        #     atexit.register(clean_process, set_logging)
        #     set_logging.wait(timeout=3) #wait for the script to finish, should take 1 second
        # except TimeoutExpired:
        #     clean_process(set_logging)
        


    # runs once per test_ function
    def tearDown(self) -> None:
        clean_process(self.launch_crazyswarm)   #kill crazyswarm_server and all of its child processes

        # #disable logging  #####this times out everytime. Where is the problem ?
        # try:
        #     command = "python3 set_parameter.py usd.logging 0"
        #     unset_logging = Popen(command, shell=True, stderr=True, stdout=PIPE, text=True,
        #                             cwd=self.ros2_ws/"src/crazyswarm2/systemtests",start_new_session=True, executable="/bin/bash")
        #     atexit.register(clean_process, unset_logging)
        #     unset_logging.wait(timeout=5) #wait for the script to finish, should take 1 second
        # except TimeoutExpired:
        #     print("unset logging timeout")
        #     clean_process(unset_logging)

        # copy .ros/log files to results folder
        if Path(Path.home() / ".ros/log").exists():
            shutil.copytree(Path.home() / ".ros/log", Path(__file__).parents[3] / f"results/{self.idFolderName()}/roslogs")
        

        #first we plot the log182 file$
        # log182 = str(self.ros2_ws / "src/crazyswarm2/systemtests/SDplotting/logs/log182")
        # log182pdf = str(self.ros2_ws / f"results/{self.idFolderName()}/log182report.pdf")
        # print("path to log182: ",log182, "path to log182pdg ", log182pdf)
        # command = f"python3 plot.py --CLImode --logfile {log182} --output {log182pdf}"
        # plot_log82 = Popen(command, shell=True, stderr=True, stdout=True, text=True,
        #                     cwd=self.ros2_ws/"src/crazyswarm2/systemtests/SDplotting", start_new_session=True, executable="/bin/bash") 
        
        print("2 ", str(self.ros2_ws) + f"/results/{self.idFolderName()}")
        ###### does this work ? normally the download should work but haven't tested if it saves in the folder correctly yet
        command = f"{self.src} && ros2 run crazyflie downloadUSDLogfile --output SDlogfile" #if CF doesn't use default URI, add --uri custom_uri (e.g --uri radio://0/80/2M/E7E7E7E70B)
        try:
            downloadSD= Popen(command, shell=True, stderr=PIPE, stdout=PIPE, text=True,         #download the log file in ....../ros2_ws/results/test_xxxxxxx/
                                cwd= self.ros2_ws / f"results/{self.idFolderName()}" ,start_new_session=True, executable="/bin/bash") 
            atexit.register(clean_process, downloadSD)
            ####testing purposes
            print("waiting")
            time_start = time.time()
            #######
            downloadSD.wait(timeout=180) #wait 10min for download to finish and raise TimeoutExpired if not finished
        except TimeoutExpired:
            clean_process(downloadSD)
            print("Downloading SD card data was killed for taking too long")

        print(f"Download finished after {time.time()-time_start}s")

        ####testing purposes
        if downloadSD.stderr != None:
            print(" download stderr : ", downloadSD.stderr.readlines())
        if downloadSD.stdout != None:
            print(" download stdout : ", downloadSD.stdout.readlines())

        ############
        #from subprocess import Popen
        

        ####try to plot the SD log
        SDlogfile_path = str(self.ros2_ws / f"/{self.idFolderName()}/SDlogfile")
        command = f"python3 plot.py --CLImode --logfile {SDlogfile_path} --output {str(self.ros2_ws)}/results/{self.idFolderName()}/SDreport.pdf"
        plot_SD = Popen(command, shell=True, stderr=True, stdout=True, text=True,
                            cwd=self.ros2_ws/"src/crazyswarm2/systemtests/SDplotting", start_new_session=True, executable="/bin/bash") 


        return super().tearDown()

        

    def record_start_and_clean(self, testname:str, max_wait:int):
        '''Starts recording the /tf topic in a rosbag, starts the test, waits, closes the rosbag and terminate all processes. max_wait is the max amount of time you want to wait 
            before killing the test flight script (in case it never terminate correctly).
            NB the testname must be the name of the crayzflie_examples executable (ie the CLI grammar "ros2 run crazyflie_examples testname" must be valid)'''
        
        try:
            command = f"{self.src} && ros2 bag record -s mcap -o test_{testname} /tf"
            record_bag =  Popen(command, shell=True, stderr=PIPE, stdout=True, text=True,
                                cwd= self.ros2_ws / "results/", start_new_session=True, executable="/bin/bash") 
            atexit.register(clean_process, record_bag)

            command = f"{self.src} && ros2 run crazyflie_examples {testname}"
            start_flight_test = Popen(command, shell=True, stderr=True, stdout=True, 
                                    start_new_session=True, text=True, executable="/bin/bash")
            atexit.register(clean_process, start_flight_test)

            start_flight_test.wait(timeout=max_wait)  #raise Timeoutexpired after max_wait seconds if start_flight_test didn't finish by itself
            clean_process(start_flight_test)          
            clean_process(record_bag)

        except TimeoutExpired:      #if max_wait is exceeded
            clean_process(start_flight_test)          
            clean_process(record_bag)

        except KeyboardInterrupt:   #if drone crashes, user can ^C to skip the waiting
            clean_process(start_flight_test)          
            clean_process(record_bag)

        #if something went wrong with the bash command lines in Popen, print the error
        if record_bag.stderr != None:
            print(testname," record_bag stderr: ", record_bag.stderr.readlines())
        if start_flight_test.stderr != None:
            print(testname," start_flight flight stderr: ", start_flight_test.stderr.readlines())


    def translate_plot_and_check(self, testname:str) -> bool :
        '''Translates rosbag .mcap format to .csv, then uses that csv to plot a pdf. Checks the deviation between ideal and real trajectories, i.e if the drone 
            successfully followed its given trajectory. Returns True if deviation < epsilon(defined in plotter_class.py) at every timestep, false if not.  '''
  
        # NB : the mcap filename is almost the same as the folder name but has _0 at the end
        inputbag = f"{str(self.ros2_ws)}/results/test_{testname}/test_{testname}_0.mcap"
        output_csv = f"{str(self.ros2_ws)}/results/test_{testname}/test_{testname}_0.csv"

        writer = McapHandler()
        writer.write_mcap_to_csv(inputbag, output_csv)  #translate bag from mcap to csv
        output_pdf = f"{str(self.ros2_ws)}/results/test_{testname}/results_{testname}.pdf"
        rosbag_csv = output_csv

        plotter = Plotter()
        plotter.create_figures(self.test_file, rosbag_csv, output_pdf) #plot the data
        return plotter.test_passed()



    def test_figure8(self):
        #set test file and folder name for this specific test
        self.test_file = "../crazyflie_examples/crazyflie_examples/data/figure8.csv"
        self.folder_name = self.idFolderName()
        print(self.id())
        print("self folder name ", self.folder_name)
        
        # run test
        self.record_start_and_clean("figure8", 20)
        #create the plot etc
        test_passed = self.translate_plot_and_check("figure8")
        #assert test_passed, "figure8 test failed : deviation larger than epsilon"

    # def test_multi_trajectory(self):
    #     #set test file and folder name for this specific test
    #     self.test_file = "../crazyflie_examples/crazyflie_examples/data/multi_trajectory/traj0.csv"
    #     self.folder_name = self.idFolderName()
    #     self.record_start_and_clean("multi_trajectory", 80)
    #     test_passed = self.translate_plot_and_check("multi_trajectory")
    #     assert test_passed, "multitrajectory test failed : deviation larger than epsilon"
        



if __name__ == '__main__':
   unittest.main()
    # setUpModule()
    # tester = TestFlights()
    # tester.setUp()
    # tester.test_figure8()
    # tester.tearDown()
    # tearDownModule()