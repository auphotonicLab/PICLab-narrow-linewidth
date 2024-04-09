import json

import matplotlib.pyplot as plt
from GUI.Functions.functions import *
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

        self.bool_save_readings = None

        self.first_time_index = 0
        
        self.power_readings = None
        self.feedback_readings = None
        
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

        self.time_start = time.strftime("%Y-%m-%d_%H-%M-%S")

        self.input_piezo_controller = self.instrument_controller.input_piezo_controller
        #self.output_piezo_controller = self.instrument_controller.output_piezo_controller
        self.target_detector = self.instrument_controller.get_target_detector()
        self.feedback_detector = self.instrument_controller.get_feedback_detector()
        
        self.x_initial = self.input_piezo_controller.get_x_voltage_set()


        self.power_readings = [[] for _ in range(len(list_of_meas_events)+1)] #The last one is not used, but is needed, as there is a short time between finishing the last measurement and finishing the total
        self.feedback_readings = [[] for _ in range(len(list_of_meas_events)+1)] #The last one is not used, but is needed, as there is a short time between finishing the last measurement and finishing the total
        self.time_stamps = [[] for _ in range(len(list_of_meas_events)+1)] #The last one is not used, but is needed, as there is a short time between finishing the last measurement and finishing the total

        

            
            
    def optimize_simple(self, start_event,list_of_meas_events, finish_event, finished_optimizing, optimize_y=True):
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

        
        self.bool_save_readings = None

        
        
        while not finish_event:
            
            self.optimize(start_event,list_of_meas_events, finish_event, finished_optimizing) #Should change finished_optimizing to True when finished optimizing.
                
            self.simple_algorithm(list_of_meas_events, finished_optimizing)
                

                
                
        self.time_end = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
        try:
            np.savetxt(fr'C:\Users\Group Login\Documents\Simon\measurementData3\Measurements_{self.time_start[:10]}\{self.time_start}_Laser_power_readings.txt', self.power_readings, fmt='%s', header = f'Simple algorithm during measurements \t time start {self.time_start}, time end {self.time_end}')
            np.savetxt(fr'C:\Users\Group Login\Documents\Simon\measurementData3\Measurements_{self.time_start[:10]}\{self.time_start}_Feedback_power_readings.txt', self.feedback_readings, fmt='%s', header = f'Simple algorithm during measurements \t time start {self.time_start}, time end {self.time_end}')

        except:
            np.savetxt(f'{self.time_start}_Laser_power_readings.txt', self.power_readings, fmt='%s', header = f'Simple algorithm during measurements \t time start {self.time_start}, time end {self.time_end}')
            np.savetxt(f'{self.time_start}_Feedback_power_readings.txt', self.feedback_readings, fmt='%s', header = f'Simple algorithm during measurements \t time start {self.time_start}, time end {self.time_end}')

        self.target_detector.closeConnection()
        self.feedback_detector.closeConnection()
        
    
    def optimize_none(self, start_event,list_of_meas_events, finish_event, finished_optimizing, optimize_y=True):
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

        
        while not finish_event:
            
            self.optimize(start_event,list_of_meas_events, finish_event, finished_optimizing) #Should change finished_optimizing to True when finished optimizing.      

            self.no_algorithm(list_of_meas_events, finished_optimizing)    
                
                
        self.time_end = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
        try:
            np.savetxt(fr'C:\Users\Group Login\Documents\Simon\measurementData3\Measurements_{self.time_start[:10]}\{self.time_start}_Laser_power_readings.txt', self.power_readings, fmt='%s', header = f'Simple algorithm during measurements \t time start {self.time_start}, time end {self.time_end}')
            np.savetxt(fr'C:\Users\Group Login\Documents\Simon\measurementData3\Measurements_{self.time_start[:10]}\{self.time_start}_Feedback_power_readings.txt', self.feedback_readings, fmt='%s', header = f'Simple algorithm during measurements \t time start {self.time_start}, time end {self.time_end}')

        except:
            np.savetxt(f'{self.time_start}_Laser_power_readings.txt', self.power_readings, fmt='%s', header = f'Simple algorithm during measurements \t time start {self.time_start}, time end {self.time_end}')
            np.savetxt(f'{self.time_start}_Feedback_power_readings.txt', self.feedback_readings, fmt='%s', header = f'Simple algorithm during measurements \t time start {self.time_start}, time end {self.time_end}')

        self.target_detector.closeConnection()
        self.feedback_detector.closeConnection()
        
        
            
    def check_measurement_number(self,list_of_meas_events):
        
        meas_no = 0
        for meas_event in list_of_meas_events:
            if meas_event.is_set():
                meas_no += 1
                
        return meas_no
    
    def save_power_readings(self, list_of_meas_events, laser_power, feedback_power):
        
            meas_no = self.check_measurement_number(list_of_meas_events)

            self.time_stamps[meas_no].append(time.time()-self.meas_time_start)
            self.power_readings[meas_no].append(laser_power)
            self.feedback_readings[meas_no].append(feedback_power)
            
    
    
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
        [current_value,current_W_value, current_feedback_value] = self.compute_function_value(current_point)
        
                
        best_point = current_point.copy()
        best_value = current_value
        best_W_value = current_W_value
    
        
        self.meas_start_time =  time.time()
        
        
        while finished_optimizing.is_set():
            
            
            current_power = self.target_detector.GetPower()
            current_feedback = self.feedback_detector.GetPower()
            
            self.save_power_readings(list_of_meas_events, current_power, current_feedback)
            
 
                
            z_change = np.array([0,0.05]) #Optimize z
            y_change = np.array([0.05,0]) #Optimize y
            
            new_point = best_point - z_change
            
            new_point[0] = np.clip(new_point[0], 0, 75)
            new_point[1] = np.clip(new_point[1], 0, 75)
            
            [new_value,new_W_value, new_feedback] = self.compute_function_value(new_point)
    

            print("New Point: ", new_point)
                    
            self.save_power_readings(list_of_meas_events, new_W_value, new_feedback)

                    
            # Update the best point if the new point has a lower function value
            if new_value < best_value:
                best_point = new_point
                best_value = new_value
                best_W_value = new_W_value
            
            else: #Checking the other z-direction
                new_point = best_point + z_change
            
                new_point[0] = np.clip(new_point[0], 0, 75)
                new_point[1] = np.clip(new_point[1], 0, 75)
            
                [new_value,new_W_value, new_feedback] = self.compute_function_value(new_point)
                
                
                print("New Point: ", new_point)
                    
                self.save_power_readings(list_of_meas_events, new_W_value, new_feedback)

                
                if new_value < best_value:
                    best_point = new_point
                    best_value = new_value
                    best_W_value = new_W_value
                
                elif optimize_y:
                    new_point = best_point - y_change
            
                    new_point[0] = np.clip(new_point[0], 0, 75)
                    new_point[1] = np.clip(new_point[1], 0, 75)
                
                    [new_value,new_W_value, new_feedback] = self.compute_function_value(new_point)
                    
                    
                    print("New Point: ", new_point)
                    
                    self.save_power_readings(list_of_meas_events, new_W_value, new_feedback)

                    
                    if new_value < best_value:
                        best_point = new_point
                        best_value = new_value
                        best_W_value = new_W_value
                    
                    else: 
                        new_point = best_point + y_change
            
                        new_point[0] = np.clip(new_point[0], 0, 75)
                        new_point[1] = np.clip(new_point[1], 0, 75)
                    
                        [new_value,new_W_value, new_feedback] = self.compute_function_value(new_point)
                        
                        print("New Point: ", new_point)
                    
                        self.save_power_readings(list_of_meas_events, new_W_value, new_feedback)

                        
                        if new_value < best_value:
                            best_point = new_point
                            best_value = new_value
                            best_W_value = new_W_value
                            
                

            self.set_point(best_point)
            
            print("New value: ", -new_value, new_W_value, "Best value: ", -best_value, best_W_value)
                    
            while_current_power = self.target_detector.GetPower()
            
            best_value = while_current_power #Making the algorithm forget it's best point
            
            while_current_feedback = self.feedback_detector.GetPower()

            self.save_power_readings(list_of_meas_events, while_current_power, while_current_feedback)


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
            
            self.save_power_readings(list_of_meas_events, current_power, current_feedback)

            time.sleep(0.2)
            
 


    def optimize(self, start_event,list_of_meas_events, finish_event, finished_optimizing):
        
        #Should probably be closer to the original thing Magnus made.


        for index in range(self.iterations):
            # Estimate the gradient at the current point
            new_point = self.optimizer.update(self.compute_function_value, current_point, current_value, index,
                                              self.fail_counter)
            new_point[0] = np.clip(new_point[0], 0, 120)
            new_point[1] = np.clip(new_point[1], 0, 120)
            new_point[2] = np.clip(new_point[2], 0, 120)
            new_point[3] = np.clip(new_point[3], 0, 120)
            new_point[4] = np.clip(new_point[4], 0, 120)
            new_point[5] = np.clip(new_point[5], 0, 120)
            new_value = self.compute_function_value(new_point)

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



        #######################################################

        self.fail_counter = 0
        
        initial_point = np.array(
            [self.input_piezo_controller.get_y_voltage_set(),
             self.input_piezo_controller.get_z_voltage_set()])
        
        print(f'This is the initial point {[self.x_initial,initial_point[0],initial_point[1]]}')
        current_point = initial_point.copy()
        [current_value,current_W_value, _] = self.compute_function_value(current_point, meas_feedback=False) #Don't care about feedback here
        
        
        best_point = current_point.copy()
        best_value = current_value
        best_W_value = current_W_value

        ##### Here the optimization should happen:
        
        if save_power_readings:
            current_power = self.target_detector.GetPower()
            current_feedback = self.feedback_detector.GetPower()

            self.save_power_readings(list_of_meas_events,current_power,current_feedback)


        
        index = 0

        while not finished_optimizing.is_set():
            
            #for index in range(int(self.iterations)):
            # Estimate the gradient at the current point
            
                if save_power_readings:
                    current_power = self.target_detector.GetPower()
                    current_feedback = self.feedback_detector.GetPower()

                    self.save_power_readings(list_of_meas_events,current_power,current_feedback)
        
                
                while_index = 0
                
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



    def set_point(self, point):
        self.input_piezo_controller.set_yz_voltage(self.x_initial, point[0], point[1])
        #self.output_piezo_controller.set_xyz_voltage(point[3], point[4], point[5])
        #input_set_thread = threading.Thread(target=self.input_piezo_controller.set_xyz_voltage, args =[point[0], point[1], point[2]])
        #output_set_thread = threading.Thread(target=self.output_piezo_controller.set_xyz_voltage, args=[point[3], point[4], point[5]])
        #input_set_thread.start()
        #output_set_thread.start()
        #input_set_thread.join()
        #output_set_thread.join()


    def compute_function_value(self, point, meas_feedback=True):
        self.set_point(point)
        time.sleep(0.001)
        value = self.target_detector.GetPower()
        
        feedback = None
        if meas_feedback:
            feedback = self.feedback_detector.GetPower()
        
        #print(f'this is the measurement: {value}')
        res = - power_W_to_dBm(value)
        #print(f'this is the optimiziation value: {res}')
        return [res, value, feedback]

    def set_optimize_bool(self, optimize_bool):
        self.optimize_bool = optimize_bool


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
        gradient_input_y, power_y, feedback_y = self.gradients(function, point, point_value,
                                          np.array([learning_rate[0], 0]))
        
        gradient_input_z, power_z, feedback_z = self.gradients(function, point, point_value,
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
        
        return first_moment, power_list, feedback_list

    def gradients(self, function, point, point_value, change):
        dh = np.linalg.norm(change)

        fx = point_value
        [fx_h, power, feedback]  = function(point - change)

        first_order = (fx - fx_h) / (dh)
        return first_order, power, feedback

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

        gradient, power_list, feedback_list = self.estimate_gradient(function, current_point,
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
        return new_point, power_list, feedback_list


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