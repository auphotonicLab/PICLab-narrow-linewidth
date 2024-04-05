# This is a sample Python script.
from ctypes import *
import sys
import pyvisa as visa

import numpy as np

rm = visa.ResourceManager()

print(rm.list_resources())

sys.path.append("C:/Users/Group Login/Documents/Simon/AU/PICLAB-main/Projects/QVersion")


from Python_lib.MDT_COMMAND_LIB import mdtListDevices
from Python_lib.MDT_COMMAND_LIB_TEST import MDT693BExample, MDT694BExample

import threading
import multiprocessing 

from GUI.Instrument_Controller import Instrument_Controller
from GUI.Optimize_Piezo import Optimize_Piezo, Optimizer_Gradient_Descent

from Python_lib.Thorlabs_PM100U import Thorlabs_PM100U


mdtLib = cdll.LoadLibrary(r"C:\Users\Group Login\Documents\Simon\AU\PICLAB-main\Projects\QVersion\Python_lib\MDT_COMMAND_LIB_x64.dll")
cmdOpen = mdtLib.Open
cmdOpen.restype = c_int
cmdOpen.argtypes = [c_char_p, c_int, c_int]

cmdIsOpen = mdtLib.IsOpen
cmdOpen.restype = c_int
cmdOpen.argtypes = [c_char_p]

cmdList = mdtLib.List
cmdList.argtypes = [c_char_p, c_int]
cmdList.restype = c_int

cmdGetId = mdtLib.GetId
cmdGetId.restype = c_int
cmdGetId.argtypes = [c_int, c_char_p]

cmdGetLimtVoltage = mdtLib.GetLimitVoltage
cmdGetLimtVoltage.restype = c_int
cmdGetLimtVoltage.argtypes = [c_int, POINTER(c_double)]

cmdSetAllVoltage = mdtLib.SetAllVoltage
cmdSetAllVoltage.restype = c_int
cmdSetAllVoltage.argtypes = [c_int, c_double]

cmdGetMasterScanEnable = mdtLib.GetMasterScanEnable
cmdGetMasterScanEnable.restype = c_int
cmdGetMasterScanEnable.argtypes = [c_int, POINTER(c_int)]

cmdSetMasterScanEnable = mdtLib.SetMasterScanEnable
cmdSetMasterScanEnable.restype = c_int
cmdSetMasterScanEnable.argtypes = [c_int, c_int]

cmdGetMasterScanVoltage = mdtLib.GetMasterScanVoltage
cmdGetMasterScanVoltage.restype = c_int
cmdGetMasterScanVoltage.argtypes = [c_int, POINTER(c_double)]

cmdSetMasterScanVoltage = mdtLib.SetMasterScanVoltage
cmdSetMasterScanVoltage.restype = c_int
cmdSetMasterScanVoltage.argtypes = [c_int, c_double]

cmdGetXAxisVoltage = mdtLib.GetXAxisVoltage
cmdGetXAxisVoltage.restype = c_int
cmdGetXAxisVoltage.argtypes = [c_int, POINTER(c_double)]

cmdSetXAxisVoltage = mdtLib.SetXAxisVoltage
cmdSetXAxisVoltage.restype = c_int
cmdSetXAxisVoltage.argtypes = [c_int, c_double]

cmdGetYAxisVoltage = mdtLib.GetYAxisVoltage
cmdGetYAxisVoltage.restype = c_int
cmdGetYAxisVoltage.argtypes = [c_int, POINTER(c_double)]

cmdSetYAxisVoltage = mdtLib.SetYAxisVoltage
cmdSetYAxisVoltage.restype = c_int
cmdSetYAxisVoltage.argtypes = [c_int, c_double]

cmdGetZAxisVoltage = mdtLib.GetZAxisVoltage
cmdGetZAxisVoltage.restype = c_int
cmdGetZAxisVoltage.argtypes = [c_int, POINTER(c_double)]

cmdSetZAxisVoltage = mdtLib.SetZAxisVoltage
cmdSetZAxisVoltage.restype = c_int
cmdSetZAxisVoltage.argtypes = [c_int, c_double]

cmdGetXAxisMinVoltage = mdtLib.GetXAxisMinVoltage
cmdGetXAxisMinVoltage.restype = c_int
cmdGetXAxisMinVoltage.argtypes = [c_int, POINTER(c_double)]

cmdSetXAxisMinVoltage = mdtLib.SetXAxisMinVoltage
cmdSetXAxisMinVoltage.restype = c_int
cmdSetXAxisMinVoltage.argtypes = [c_int, c_double]

cmdGetYAxisMinVoltage = mdtLib.GetYAxisMinVoltage
cmdGetYAxisMinVoltage.restype = c_int
cmdGetYAxisMinVoltage.argtypes = [c_int, POINTER(c_double)]

cmdSetYAxisMinVoltage = mdtLib.SetYAxisMinVoltage
cmdSetYAxisMinVoltage.restype = c_int
cmdSetYAxisMinVoltage.argtypes = [c_int, c_double]

cmdGetZAxisMinVoltage = mdtLib.GetZAxisMinVoltage
cmdGetZAxisMinVoltage.restype = c_int
cmdGetZAxisMinVoltage.argtypes = [c_int, POINTER(c_double)]

cmdSetZAxisMinVoltage = mdtLib.SetZAxisMinVoltage
cmdSetZAxisMinVoltage.restype = c_int
cmdSetZAxisMinVoltage.argtypes = [c_int, c_double]

cmdGetXAxisMaxVoltage = mdtLib.GetXAxisMaxVoltage
cmdGetXAxisMaxVoltage.restype = c_int
cmdGetXAxisMaxVoltage.argtypes = [c_int, POINTER(c_double)]

cmdSetXAxisMaxVoltage = mdtLib.SetXAxisMaxVoltage
cmdSetXAxisMaxVoltage.restype = c_int
cmdSetXAxisMaxVoltage.argtypes = [c_int, c_double]

cmdGetYAxisMaxVoltage = mdtLib.GetYAxisMaxVoltage
cmdGetYAxisMaxVoltage.restype = c_int
cmdGetYAxisMaxVoltage.argtypes = [c_int, POINTER(c_double)]

cmdSetYAxisMaxVoltage = mdtLib.SetYAxisMaxVoltage
cmdSetYAxisMaxVoltage.restype = c_int
cmdSetYAxisMaxVoltage.argtypes = [c_int, c_double]

cmdGetZAxisMaxVoltage = mdtLib.GetZAxisMaxVoltage
cmdGetZAxisMaxVoltage.restype = c_int
cmdGetZAxisMaxVoltage.argtypes = [c_int, POINTER(c_double)]

cmdSetZAxisMaxVoltage = mdtLib.SetZAxisMaxVoltage
cmdSetZAxisMaxVoltage.restype = c_int
cmdSetZAxisMaxVoltage.argtypes = [c_int, c_double]

cmdGetVoltageAdjustmentResolutione = mdtLib.GetVoltageAdjustmentResolution
cmdGetVoltageAdjustmentResolutione.restype = c_int
cmdGetVoltageAdjustmentResolutione.argtypes = [c_int, POINTER(c_int)]

cmdSetVoltageAdjustmentResolution = mdtLib.SetVoltageAdjustmentResolution
cmdSetVoltageAdjustmentResolution.restype = c_int
cmdSetVoltageAdjustmentResolution.argtypes = [c_int, c_int]

cmdGetXYZAxisVoltage = mdtLib.GetXYZAxisVoltage
cmdGetXYZAxisVoltage.restype = c_int
cmdGetXYZAxisVoltage.argtypes = [c_int, POINTER(c_double), POINTER(c_double), POINTER(c_double)]

cmdSetXYZAxisVoltage = mdtLib.SetXYZAxisVoltage
cmdSetXYZAxisVoltage.restype = c_int
cmdSetXYZAxisVoltage.argtypes = [c_int, c_double, c_double, c_double]


# endregion
def mdtListDevices():
    """ List all connected MDT devices
    Returns: 
       The mdt device list, each device item is [serialNumber, mdtType]
    """
    str = create_string_buffer(10240, '\0')
    result = cmdList(str, 10240)
    devicesStr = str.raw.decode("utf-8").rstrip('\x00').split(',')
    length = len(devicesStr)
    i = 0
    devices = []
    devInfo = ["", ""]
    MDTTypeList = ["MDT693B", "MDT694B"]
    while (i < length):
        str = devicesStr[i]
        if (i % 2 == 0):
            if str != '':
                devInfo[0] = str
            else:
                i += 1
        else:
            isFind = False
            for mt in MDTTypeList:
                if (str.find(mt) >= 0):
                    str = mt
                    isFind = True;
                    break
            if (isFind):
                devInfo[1] = str
                devices.append(devInfo.copy())
        i += 1
    return devices



def main():
    print("*** MDT device python example ***")
    try:
        devs = mdtListDevices()
        print(devs)
        if len(devs) <= 0:
            print('There are no devices connected')
            sys.exit()

        for mdt in devs:
            if mdt[1] == "MDT693B":
                MDT693BExample(mdt[0])
            elif mdt[1] == "MDT694B":
                MDT694BExample(mdt[0])
    except Exception as ex:
        print("Warning:", ex)
    print("*** End ***")
    input()
    
    sys.exit()


#print(mdtListDevices())


#main()



instrument_controller = Instrument_Controller()


def instrument_on():
    is_instruments_on = False
    return is_instruments_on

settings = r'C:\Users\Group Login\Documents\Simon\AU\optimize_piezo_settings'
optimizer = Optimizer_Gradient_Descent(settings)
optimize_piezo = Optimize_Piezo(instrument_controller, optimizer, settings)
        
        

def optimize_y_and_z():
    open_instruments()
    start_event =  multiprocessing.Event()
    
    finish_event = multiprocessing.Event()
    
    list_of_measurements = [start_event, finish_event]
    
    start_event.set()

    piezo_optimization_thread = threading.Thread(target=optimize_piezo.optimize_simple, args=(start_event,list_of_measurements,finish_event))
    piezo_optimization_thread.start()
    
    time.sleep(20)
    finish_event.set()


def open_instruments():
    
    is_instruments_on = instrument_on()
    if not is_instruments_on:
        is_instruments_on = True
        instrument_controller.open_instruments()

'''import pyvisa as visa
rm = visa.ResourceManager()


feedback = Thorlabs_PM100U(rm,0,'s',PM_index=0)
power = Thorlabs_PM100U(rm,0,'s',PM_index=1)
'''
#optimize_y_and_z()

#np.savetxt('Power_readings_optimization_loop.txt',optimize_piezo.power_readings,header =f'Start of the optimization {optimize_piezo.time_start},\n end of the optimization:{optimize_piezo.time_end}') 
