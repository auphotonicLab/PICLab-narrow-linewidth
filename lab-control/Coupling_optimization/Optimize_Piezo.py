import json

import numpy as np
from GUI.Functions.functions import power_W_to_dBm
import time

class Optimize_Piezo:

    def __init__(self, instrument_controller, optimizer, settings_path):
        self.optimize_bool = True
        self.fail_counter = None
        self.x_initial = 0
        self.settings_path = settings_path
        self.target_detector = None
        self.feedback_detector = None
        self.input_piezo_controller = None
        self.output_piezo_controller = None
        self.instrument_controller = instrument_controller
        self.optimizer = optimizer

        self.meas_feedback_bool = None   #Remember to change this, if wanting to measure feedback power in "compute_function_value" method
        self.power_readings = None
        self.feedback_readings = None
        
        self.adv_power_readings = None #For saving power readings during the advanced optimization
        self.adv_time_stamps = None #And the time stamps as well.

        self.meas_time_start = None
        self.time_stamps = None        
        
        self.time_start = None
        self.time_end = None

        with open(self.settings_path, "r") as text_file:
            settings_dict = json.load(text_file)
            self.iterations = settings_dict["iterations"]
            self.abs_tol = settings_dict["abs_tol"]
            self.fail_limit = settings_dict["fail_limit"]
            self.min_sample_time = settings_dict["min_sample_time"]
            self.max_sample_time = settings_dict["max_sample_time"]


    def initialize_optimization(self, list_of_meas_events):



        self.input_piezo_controller = self.instrument_controller.input_piezo_controller
        #self.output_piezo_controller = self.instrument_controller.output_piezo_controller
        self.target_detector = self.instrument_controller.get_target_detector()
        self.feedback_detector = self.instrument_controller.get_feedback_detector()
        
        self.x_initial = self.input_piezo_controller.get_x_voltage_set()


        self.power_readings = [[] for _ in range(len(list_of_meas_events)+1)]
        self.feedback_readings = [[] for _ in range(len(list_of_meas_events)+1)]
        self.time_stamps = [[] for _ in range(len(list_of_meas_events)+1)]

        self.adv_power_readings = [[] for _ in range(len(list_of_meas_events)+1)]
        self.adv_time_stamps = [[] for _ in range(len(list_of_meas_events)+1)]

        time.sleep(1) #To ensure that the system is stable and that the powermeters have had sufficient time to connect.

        self.time_start = time.strftime("%Y-%m-%d_%H-%M-%S")
        self.meas_time_start = time.time()

                
    def check_measurement_number(self,list_of_meas_events):
        
        meas_no = 0
        for meas_event in list_of_meas_events:
            if meas_event.is_set():
                meas_no += 1
                
        return meas_no
    
    def save_power_readings(self, list_of_meas_events, laser_power, feedback_power, aux_time_saver):
        '''
        For saving power and feedback readings during measurements.
        Important to update aux_time_saver with the time when the power reading was taken!
        '''
    
        meas_no = self.check_measurement_number(list_of_meas_events)

        self.time_stamps[meas_no].append(aux_time_saver-self.meas_time_start)
        self.power_readings[meas_no].append(laser_power)
        self.feedback_readings[meas_no].append(feedback_power)


    def adv_save_power_readings(self, list_of_meas_events, laser_power, aux_time_saver):
        '''
        For saving the power readings during the advanced optimization
        '''
        meas_no = self.check_measurement_number(list_of_meas_events)

        self.adv_time_stamps[meas_no].append(aux_time_saver-self.meas_time_start)
        self.adv_power_readings[meas_no].append(laser_power)



    def set_point(self, point):
        self.input_piezo_controller.set_yz_voltage(self.x_initial, point[0], point[1])
        #self.output_piezo_controller.set_xyz_voltage(point[3], point[4], point[5])
        #input_set_thread = threading.Thread(target=self.input_piezo_controller.set_xyz_voltage, args =[point[0], point[1], point[2]])
        #output_set_thread = threading.Thread(target=self.output_piezo_controller.set_xyz_voltage, args=[point[3], point[4], point[5]])
        #input_set_thread.start()
        #output_set_thread.start()
        #input_set_thread.join()
        #output_set_thread.join()


    def compute_function_value(self, point):
        self.set_point(point)
        time.sleep(0.001)
        
        feedback = None
        value = self.target_detector.GetPower()
        
        if self.meas_feedback_bool:
            feedback = self.feedback_detector.GetPower()
        
        aux_time_saver = time.time()
        
        #print(f'this is the measurement: {value}')
        res = - power_W_to_dBm(value)
        #print(f'this is the optimiziation value: {res}')
        return [res, value, feedback, aux_time_saver]

    def set_optimize_bool(self, optimize_bool):
        self.optimize_bool = optimize_bool


    def save_files(self, pipe_receiver):

        self.time_end = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())

        index, path = pipe_receiver.recv()

        try:
            np.savetxt(f'{path}\\{self.time_start}_Laser_power_readings.txt', (self.power_readings[index],self.time_stamps[index]), fmt='%s', header = f'[Power,time] during measurements \t time start {self.time_start}, time end {self.time_end}')
            np.savetxt(f'{path}\\{self.time_start}_Feedback_power_readings.txt', (self.feedback_readings[index],self.time_stamps[index]), fmt='%s', header = f'[Power,time]  during measurements \t time start {self.time_start}, time end {self.time_end}')

            np.savetxt(f'{path}\\{self.time_start}_Adv_laser_power_readings.txt', (self.adv_power_readings[index],self.adv_time_stamps[index]), fmt='%s', header = f'[Power,time] readings during advanced optimization algorithm \t time start {self.time_start}, time end {self.time_end}')

        except:
            
            np.savetxt(fr'{path}\{self.time_start}_Laser_power_readings.txt', (self.power_readings[index],self.time_stamps[index]), fmt='%s', header = f'[Power,time] during measurements, [power, time] pr. line \t time start {self.time_start}, time end {self.time_end}')
            np.savetxt(fr'{path}\{self.time_start}_Feedback_power_readings.txt', (self.feedback_readings[index],self.time_stamps[index]), fmt='%s', header = f'[Power,time] during measurements [power, time] \t time start {self.time_start}, time end {self.time_end}')

            np.savetxt(fr'{path}\{self.time_start}_Adv_laser_power_readings.txt', (self.adv_power_readings[index],self.adv_time_stamps[index]), fmt='%s', header = f'[Power,time] readings during advanced optimization algorithm [power,time] \t time start {self.time_start}, time end {self.time_end}')




            
    def optimize_simple(self, list_of_meas_events, finished_optimizing, pipe_receiver, saved_the_data, optimize_y=True):
        """
        Optimization method that uses the advanced optimization algorithm inbetween measurements and then uses the simple algorithm during the measurements.

        Parameters
        ----------
        start_event : Multiprocessing.Event
            If .is_set()=True, the measurements have begun and the power and feedback readings are saved in a list.
            
        list_of_meas_events : list
            A list of all measurements events. The amount that has .is_set()=True is equal to the current measurement number.
            
        finish_event : Multiprocessing.Event
            If .is_set()=True, the measurements have stopped and the optimization is told to stop.
            
        finished_optimizing: Multiprocessing.Event
            If .is_set()=False, the advanced optimization algorithm should run. When finished optimizing it changes .is_set()=True and the simple algorithm runs and the power readings are saved. 
            
        optimize_y : Boolean, optional
            If True, the algorithm will move the piezo stage in the +/- y-direction. If false, it will only move the z-direciton.

        Returns
        -------
        None.

        """
        self.initialize_optimization(list_of_meas_events)

        meas_no = int(len(list_of_meas_events)/2)*2
        
        
        for _ in range(meas_no):


            self.meas_feedback_bool = False
            self.optimize(list_of_meas_events, finished_optimizing) #Should change finished_optimizing to True when finished optimizing.
            
            self.meas_feedback_bool = True
            self.simple_algorithm(list_of_meas_events, finished_optimizing)

            self.save_files(pipe_receiver)

            saved_the_data.set()

            
        self.target_detector.closeConnection()
        self.feedback_detector.closeConnection()
        
    
    def optimize_none(self, list_of_meas_events, finished_optimizing, pipe_receiver, saved_the_data, optimize_y=True):
        """
        Optimization method that uses the advanced optimization algorithm inbetween measurements and nothing during the measurements.

        Parameters
        ----------
        start_event : Multiprocessing.Event
            If .is_set()=True, the measurements have begun and the power and feedback readings are saved in a list.
            
        list_of_meas_events : list
            A list of all measurements events. The amount that has .is_set()=True is equal to the current measurement number.
            
        finish_event : Multiprocessing.Event
            If .is_set()=True, the measurements have stopped and the optimization is told to stop.
            
        finished_optimizing: Multiprocessing.Event
            If .is_set()=False, the advanced optimization algorithm should run. When finished optimizing it changes .is_set()=True and no optimization runs and the power readings are saved. 
            
        optimize_y : Boolean, optional
            If True, the algorithm will move the piezo stage in the +/- y-direction. If false, it will only move the z-direciton.

        Returns
        -------
        None.

        """

        self.initialize_optimization(list_of_meas_events)

        
        for _ in range(len(list_of_meas_events)): #Could include an index and ditch the "check_meas_no" method.

            self.meas_feedback_bool = False
            self.optimize(list_of_meas_events, finished_optimizing) #Should change finished_optimizing to True when finished optimizing.      

            self.meas_feedback_bool = True
            self.no_algorithm(list_of_meas_events, finished_optimizing)

            self.save_files(pipe_receiver)

            saved_the_data.set()


        self.target_detector.closeConnection()
        self.feedback_detector.closeConnection()
            
    
    
    def simple_algorithm(self, list_of_meas_events, finished_optimizing, optimize_y=True):
        '''
        A simple algorithm, that only moves in the negative and positive z-direction (and y-direction if optimize_y is True) in small steps of 0.1V on the Piezo controller.
        
        It measures a 'best point' and then tries to find a greater value by first moving -0.1V in z-direction. If that's not greater, reset then move to +0.1V. If that's not greater; reset then move in -0.1V in y-direction and lastly reset and move in +0.1V if previous change is not greater than best value.
        
        When this has run, measure a new 'best point' and keep going until finish_event.is_set()=True.
        

        Parameters
        ----------
        start_event : Multiprocessing.Event
            If .is_set()=True, the measurements have begun and the power and feedback readings are saved in a list.
            
        list_of_meas_events : list
            A list of all measurements events. The amount that has .is_set()=True is equal to the current measurement number.
            
        finish_event : Multiprocessing.Event
            If .is_set()=True, the measurements have stopped and the optimization is told to stop.
            
        optimize_y : Boolean, optional
            If True, the algorithm will move the piezo stage in the +/- y-direction. If false, it will only move the z-direciton.

        Returns
        -------
        None.

        '''

       
        initial_point = np.array(
            [self.input_piezo_controller.get_y_voltage_set(),
             self.input_piezo_controller.get_z_voltage_set()])
        
        print(f'This is the initial point {[self.x_initial,initial_point[0],initial_point[1]]}')
        current_point = initial_point.copy()
        [current_value,current_W_value, current_feedback_value, aux_time_saver] = self.compute_function_value(current_point)
        
        self.save_power_readings(list_of_meas_events, current_W_value, current_feedback_value, aux_time_saver)

                
        best_point = current_point.copy()
        best_value = current_value
        best_W_value = current_W_value
    
        
        
        
        
        while finished_optimizing.is_set():
            
            
            current_power = self.target_detector.GetPower()
            current_feedback = self.feedback_detector.GetPower()
            aux_time_saver = time.time()
            
            self.save_power_readings(list_of_meas_events, current_power, current_feedback, aux_time_saver)
            
 
                
            z_change = np.array([0,0.05]) #Optimize z
            y_change = np.array([0.05,0]) #Optimize y
            
            new_point = best_point - z_change
            
            new_point[0] = np.clip(new_point[0], 0, 75)
            new_point[1] = np.clip(new_point[1], 0, 75)
            
            [new_value,new_W_value, new_feedback, aux_time_saver] = self.compute_function_value(new_point)
    

            print("New Point: ", new_point)
                    
            self.save_power_readings(list_of_meas_events, new_W_value, new_feedback, aux_time_saver)

                    
            # Update the best point if the new point has a lower function value
            if new_value < best_value:
                best_point = new_point
                best_value = new_value
                best_W_value = new_W_value
            
            else: #Checking the other z-direction
                new_point = best_point + z_change
            
                new_point[0] = np.clip(new_point[0], 0, 75)
                new_point[1] = np.clip(new_point[1], 0, 75)
            
                [new_value,new_W_value, new_feedback, aux_time_saver] = self.compute_function_value(new_point)
                
                
                print("New Point: ", new_point)
                    
                self.save_power_readings(list_of_meas_events, new_W_value, new_feedback, aux_time_saver)

                
                if new_value < best_value:
                    best_point = new_point
                    best_value = new_value
                    best_W_value = new_W_value
                
                elif optimize_y:
                    new_point = best_point - y_change
            
                    new_point[0] = np.clip(new_point[0], 0, 75)
                    new_point[1] = np.clip(new_point[1], 0, 75)
                
                    [new_value,new_W_value, new_feedback, aux_time_saver] = self.compute_function_value(new_point)
                    
                    
                    print("New Point: ", new_point)
                    
                    self.save_power_readings(list_of_meas_events, new_W_value, new_feedback, aux_time_saver)

                    
                    if new_value < best_value:
                        best_point = new_point
                        best_value = new_value
                        best_W_value = new_W_value
                    
                    else: 
                        new_point = best_point + y_change
            
                        new_point[0] = np.clip(new_point[0], 0, 75)
                        new_point[1] = np.clip(new_point[1], 0, 75)
                    
                        [new_value,new_W_value, new_feedback, aux_time_saver] = self.compute_function_value(new_point)
                        
                        print("New Point: ", new_point)
                    
                        self.save_power_readings(list_of_meas_events, new_W_value, new_feedback, aux_time_saver)

                        
                        if new_value < best_value:
                            best_point = new_point
                            best_value = new_value
                            best_W_value = new_W_value
                            
                

            self.set_point(best_point)
            
            print("New value: ", -new_value, new_W_value, "Best value: ", -best_value, best_W_value)
                    
            while_current_power = self.target_detector.GetPower()
            
            best_value = while_current_power #Making the algorithm forget it's best point
            
            while_current_feedback = self.feedback_detector.GetPower()
            aux_time_saver = time.time()

            self.save_power_readings(list_of_meas_events, while_current_power, while_current_feedback, aux_time_saver)


    def no_algorithm(self, list_of_meas_events, finished_optimizing):
        
        '''
        This is only for saving power readings and it keeps going until finished_optimizing.is_set()=False, which the measurement process will do.
        

        Parameters
        ----------
        start_event : Multiprocessing.Event
            If .is_set()=True, the measurements have begun and the power and feedback readings are saved in a list.
            
        list_of_meas_events : list
            A list of all measurements events. The amount that has .is_set()=True is equal to the current measurement number.
            
        finish_event : Multiprocessing.Event
            If .is_set()=True, the measurements have stopped and the optimization is told to stop.
            
        optimize_y : Boolean, optional
            If True, the algorithm will move the piezo stage in the +/- y-direction. If false, it will only move the z-direciton.

        Returns
        -------
        None.
        '''

        while finished_optimizing.is_set():
            
            current_power = self.target_detector.GetPower()
            current_feedback = self.feedback_detector.GetPower()
            aux_time_saver = time.time()
            
            self.save_power_readings(list_of_meas_events, current_power, current_feedback, aux_time_saver)

            time.sleep(0.2)
            
 


    def optimize(self, list_of_meas_events, finished_optimizing):
        
        #Should probably be closer to the original thing Magnus made.

        self.fail_counter = 0
        
        initial_point = np.array(
            [self.input_piezo_controller.get_y_voltage_set(),
             self.input_piezo_controller.get_z_voltage_set()])
        
        print(f'This is the initial point {[self.x_initial,initial_point[0],initial_point[1]]}')
        current_point = initial_point.copy()
        [current_value,current_W_value, _, aux_time_saver] = self.compute_function_value(current_point) #Don't care about feedback here
        
        self.adv_save_power_readings(list_of_meas_events,current_W_value, aux_time_saver)
        
        best_point = current_point.copy()
        best_value = current_value

        
        index = 0

        for index in range(self.iterations):
            # Estimate the gradient at the current point
            new_point, power_list, _, time_list = self.optimizer.update(self.compute_function_value, current_point, current_value, index,
                                            self.fail_counter)
            
            for i in range(len(power_list)):
                self.adv_save_power_readings(list_of_meas_events, power_list[i], time_list[i])

            new_point[0] = np.clip(new_point[0], 0, 75)
            new_point[1] = np.clip(new_point[1], 0, 75)

            [new_value,new_W_value, _, aux_time_saver] = self.compute_function_value(new_point)

            self.adv_save_power_readings(list_of_meas_events, new_W_value, aux_time_saver)

            print("New Point: ", new_point)
                    
            # Update the best point if the new point has a lower function value
            if new_value < best_value:
                self.fail_counter = 0
                best_point = new_point
                best_value = new_value
            else:
                if new_value > current_value:
                    print("fail")
                    self.fail_counter = self.fail_counter + 1

            if self.fail_counter >= self.fail_limit:
                print("fail_counter")
                break

            if not self.optimize_bool:
                break

            print("New value: ", new_value, "Best value: ", best_value)

            # Check for convergence based on absolute and relative tolerances
            change = np.linalg.norm(new_value - current_value)
            if change < self.abs_tol:
                print("tolerance")
                break

            current_point = new_point
            current_value = new_value

        self.set_point(best_point)

        finished_optimizing.set()


'''
                while_current_power = self.target_detector.GetPower()

                if save_power_readings:
                    while_current_feedback = self.feedback_detector.GetPower()
                    self.save_power_readings(start_event, list_of_meas_events, while_current_power, while_current_feedback)


                while while_current_power < 3.62e-05:
            
                    new_point, power_list, feedback_list = self.optimizer.update(self.compute_function_value, current_point, current_value, while_index,
                                                      self.fail_counter)
                    new_point[0] = np.clip(new_point[0], 0, 75)
                    new_point[1] = np.clip(new_point[1], 0, 75)
    

                    for i in range(len(power_list)):
                        self.save_power_readings(start_event, list_of_meas_events, power_list[i], feedback_list[i])

                    [new_value,new_W_value, _] = self.compute_function_value(new_point)
        
                    print("New Point: ", new_point)
                    
                    
                    # Update the best point if the new point has a lower function value
                    if new_value < best_value:
                        self.fail_counter = 0
                        best_point = new_point
                        best_value = new_value
                        best_W_value = new_W_value
                    else:
                        if new_value > current_value:
                            print("fail")
                            self.fail_counter = self.fail_counter + 1
        
                    if self.fail_counter >= self.fail_limit:
                        print("fail_counter")
                        break
        
                    if not self.optimize_bool:
                        break
        
                    print("New value: ", -new_value, new_W_value, "Best value: ", -best_value, best_W_value)
        
                    # Check for convergence based on absolute and relative tolerances
                    change = np.linalg.norm(new_value - current_value)
                    if change < self.abs_tol:
                        print("tolerance")
                        break
        
                    current_point = new_point
                    current_value = new_value
                    
                    while_index +=1
                    
                    while_current_power = self.target_detector.GetPower()
       
                self.set_point(best_point)
                
                index += 1
'''

class Optimizer_Gradient_Descent:

    def __init__(self, settings_path):
        self.settings_path = settings_path

        self.m = None
        self.v = None
        self.m_hat = None
        self.v_hat = None

    def estimate_gradient(self, function, point, point_value, learning_rate):
        #gradient_input_x = self.gradients(function, point, point_value,
            #                              np.array([learning_rate[0], 0, 0, 0, 0, 0]))
        gradient_input_y, power_y, feedback_y, time_y = self.gradients(function, point, point_value,
                                          np.array([learning_rate[0], 0]))
        
        gradient_input_z, power_z, feedback_z, time_z = self.gradients(function, point, point_value,
                                          np.array([0,learning_rate[1]]))
        
        #gradient_output_x = self.gradients(function, point, point_value,
           #                                np.array([0, 0, 0, learning_rate[3], 0, 0]))
        #gradient_output_y = self.gradients(function, point, point_value,
          #                                 np.array([0, 0, 0, 0, learning_rate[4], 0]))
        #gradient_output_z = self.gradients(function, point, point_value,
         #                                  np.array([0, 0, 0, 0, 0, learning_rate[5]]))

        first_moment = np.array(
            [gradient_input_y, gradient_input_z])# gradient_output_x, gradient_output_y,
             #gradient_output_z])
        
        power_list = [power_y, power_z]
        feedback_list = [feedback_y, feedback_z]
        time_list = [time_y,time_z]
        
        return first_moment, power_list, feedback_list, time_list

    def gradients(self, function, point, point_value, change):
        dh = np.linalg.norm(change)

        fx = point_value
        [fx_h, power, feedback, aux_time_saver]  = function(point - change)

        first_order = (fx - fx_h) / (dh)
        return first_order, power, feedback, aux_time_saver

    def update(self, function, current_point, current_value, index, fail_counter):
        if self.m is None:
            self.m = np.zeros_like(current_point)  # First moment estimate
            self.v = np.zeros_like(current_point)  # Second moment estimate

        with open(self.settings_path, "r") as text_file:
            settings_dict = json.load(text_file)
            learning_rate = np.array(settings_dict["learning_rate"])
            gradient_estimation = np.array(settings_dict["gradient_estimation"]) / np.sqrt(fail_counter + 1)
            beta1 = settings_dict["beta1"]
            beta2 = settings_dict["beta2"]
            epsilon = settings_dict["epsilon"]

        gradient, power_list, feedback_list, time_list = self.estimate_gradient(function, current_point,
                                          current_value, gradient_estimation)

        print("Gradient: ", gradient)
        # Update the first moment estimate
        self.m = beta1 * self.m + (1 - beta1) * gradient
        # Update the second moment estimate
        self.v = beta2 * self.v + (1 - beta2) * gradient ** 2
        # Bias-corrected moment estimates
        self.m_hat = self.m / (1 - beta1 ** (index + 1))
        self.v_hat = self.v / (1 - beta2 ** (index + 1))

        change = learning_rate * self.m_hat / (np.sqrt(self.v_hat) + epsilon)
        new_point = current_point - change
        return new_point, power_list, feedback_list, time_list


class Optimizer_Coordinate:

    def __init__(self, settings_path):
        self.settings_path = settings_path
        self.second_gradient_list = []
        self.first_gradient_list = []
        self.point_list = []
        self.point_x_list = []
        self.point_y_list = []
        self.value_list = []
        self.max_index_list = []

        with open(self.settings_path, "r") as text_file:
            settings_dict = json.load(text_file)
            self.learning_rate = np.array(settings_dict["single_learning_rate"])

    def estimate_gradient(self):
        new_gradient = None
        new_second_gradient = None

        if len(self.value_list) == 1:
            new_gradient = self.first_gradient_list[0].copy()
            new_second_gradient = self.first_gradient_list[0].copy()
        else:
            current_second_gradient = self.second_gradient_list[-2]
            current_gradient = self.first_gradient_list[-1]
            previous_point = self.point_list[-2]
            current_point = self.point_list[-1]
            previous_value = self.value_list[-2]
            current_value = self.value_list[-1]
            max_index = self.max_index_list[-1]

            new_gradient = current_gradient.copy()
            new_gradient[max_index] = (current_value - previous_value) / (
                    current_point[max_index] - previous_point[max_index])

            new_second_gradient = current_second_gradient.copy()
            new_second_gradient[max_index] = (new_gradient[max_index] - current_gradient[
                max_index]) / (current_point[max_index] - previous_point[max_index])

        return np.array(new_gradient), np.array(new_second_gradient)

    def update(self, function, current_point, current_value, index):
        if len(self.value_list) == 0:
            self.value_list.append(current_value)
            self.point_list.append(current_point * 1.0)
            self.first_gradient_list.append(current_point * 0.1)
            self.second_gradient_list.append(current_point * 0.1)
        new_gradient, new_second_gradient = self.estimate_gradient()
        max_index = np.argmax(np.abs(new_gradient))

        new_point = current_point.copy() * 1.0
        new_point[max_index] = current_point[max_index] - self.learning_rate * new_gradient[max_index]
        new_value = function(new_point)
        self.first_gradient_list.append(new_gradient.copy())
        self.second_gradient_list.append(new_second_gradient.copy())
        self.point_x_list.append(new_point[0])
        self.point_y_list.append(new_point[1])
        self.point_list.append(new_point.copy())
        self.value_list.append(new_value.copy())
        self.max_index_list.append(max_index)

        return new_point

class Optimizer_Seperate_Coordinate:

    def __init__(self, settings_path):
        self.settings_path = settings_path
        self.second_gradient_list = []
        self.first_gradient_list = []
        self.point_list = []
        self.point_x_list = []
        self.point_y_list = []
        self.value_list = []
        self.max_index_list = []

        with open(self.settings_path, "r") as text_file:
            settings_dict = json.load(text_file)
            self.learning_rate = np.array(settings_dict["single_learning_rate"])

        while True:
            pass

    def update(self, function, current_point, current_value, index):
        pass