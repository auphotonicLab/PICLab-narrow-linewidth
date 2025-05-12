Analysis Tools
=============

This section contains various tools for analyzing laser measurements and data processing.

Optical Spectrum Analysis
------------------------

The OSA (Optical Spectrum Analyzer) module provides functionality for loading, processing, and visualizing data from Optical Spectrum Analyzers. It includes tools for:

* Loading OSA data from single files or directories
* Processing wavelength and power measurements
* Plotting optical spectra with customizable parameters
* Handling metadata from OSA measurements

Key Methods
~~~~~~~~~~

* ``load_osa_data(file_path)``: Loads OSA data from a single file, extracting wavelength and power measurements and metadata. Returns wavelengths (nm), power (dBm), and metadata.

* ``process_osa_directory(directory_path)``: Processes all OSA data files in a directory, handling errors gracefully. Returns a list of processed data tuples.

* ``plot_osa_spectrum(wavelengths, power, title=None, ylim=None, save_path=None)``: Creates standardized plots of optical spectrum data with proper labeling and optional customization.

* ``process_and_plot_osa_data(data_path, plot=True, save_plots=False, output_dir=None)``: High-level function that combines loading, processing, and plotting functionality for both single files and directories.

Complete API Reference
~~~~~~~~~~~~~~~~~~~~

.. currentmodule:: u_shaped_lib.OSA

.. autofunction:: load_osa_data
.. autofunction:: process_osa_directory
.. autofunction:: plot_osa_spectrum
.. autofunction:: process_and_plot_osa_data

Noise Analysis
-------------

The RIN (Relative Intensity Noise) module provides comprehensive tools for analyzing Relative Intensity Noise in optical systems. Key features include:

* Calibration of optical-to-electrical conversion
* Processing of RIN measurements from ESA (Electrical Spectrum Analyzer) data
* Calculation of single RIN values and statistical analysis
* Visualization of RIN spectra with background comparison
* Conversion utilities between linear and dB scales

Key Methods
~~~~~~~~~~

Calibration and Conversion
^^^^^^^^^^^^^^^^^^^^^^^^^

* ``calibrate_conversion(power_uW, voltage_mV)``: Performs linear fit to determine conversion factor between optical power and electrical voltage measurements.

* ``convert_optical_to_electrical(power, conversion_factor, impedance=50.0, ret_V=False)``: Converts optical power to electrical power (dBm) or voltage (V) using calibration factor.

Data Processing
^^^^^^^^^^^^^

* ``process_intensity_data(path, conversion_factor, power=None)``: Processes intensity data from a single file, applying RBW correction and conversion.

* ``calculate_single_RIN(xs, ys, start_idx=10)``: Calculates single RIN value from frequency and RIN data.

* ``get_RIN_data(directory, conversion_factor, background_identifier, background_power, plot=True, start_idx=None)``: Processes and gets RIN data from a directory, including background subtraction.

Utility Functions
^^^^^^^^^^^^^^^

* ``ratio_to_db(feedback_power, output_power, min_power=0.000003)``: Converts power ratio to dB.

* ``linear_to_dB(datapoint_linear)``: Converts linear power to dB.

* ``dB_to_linear(power)``: Converts dB to linear power.

Visualization
^^^^^^^^^^^

* ``plot_RIN_data(xs_list, ys_list, rbw, background_idx=None)``: Creates standardized plots of RIN data with proper formatting and optional background comparison.

Complete API Reference
~~~~~~~~~~~~~~~~~~~~

.. currentmodule:: u_shaped_lib.RIN

.. autofunction:: calibrate_conversion
.. autofunction:: convert_optical_to_electrical
.. autofunction:: process_intensity_data
.. autofunction:: calculate_single_RIN
.. autofunction:: get_RIN_data
.. autofunction:: ratio_to_db
.. autofunction:: linear_to_dB
.. autofunction:: dB_to_linear
.. autofunction:: plot_RIN_data

Frequency Stability Analysis
--------------------------

The Beatnote Drift module provides tools for analyzing and visualizing beatnote drift measurements in optical systems. Key features include:

* Loading and parsing beatnote measurement data
* Processing time-dependent frequency and power measurements
* Statistical analysis of frequency drift (mean, standard deviation, peak-to-peak)
* Visualization of drift and power data with customizable units
* Support for various data formats and conversion factors

Key Methods
~~~~~~~~~~

Data Loading and Processing
^^^^^^^^^^^^^^^^^^^^^^^^^

* ``load_beatnote_data(filepath)``: Loads beatnote data from a file, extracting timestamps, frequencies, and power measurements.

* ``process_beatnote_data(timestamps, frequencies, powers, freq_conversion=1e-9, power_conversion=20/1000)``: Processes raw beatnote data with unit conversions and organizes into a dictionary format.

Analysis
^^^^^^^

* ``analyze_beatnote_drift(freq_drift)``: Calculates statistical measures of frequency drift, including mean, standard deviation, and peak-to-peak values.

Visualization
^^^^^^^^^^^

* ``plot_beatnote_data(processed_data, freq_ylim=None, power_ylim=None, title=None, save_path=None)``: Creates a figure with two subplots showing frequency drift and power measurements over time.

Complete API Reference
~~~~~~~~~~~~~~~~~~~~

.. currentmodule:: u_shaped_lib.beatnote_drift

.. autofunction:: load_beatnote_data
.. autofunction:: process_beatnote_data
.. autofunction:: analyze_beatnote_drift
.. autofunction:: plot_beatnote_data
.. autofunction:: analyze_and_plot_beatnote

Linewidth Analysis
----------------

.. automodule:: u_shaped_lib.fit_functions
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: u_shaped_lib.lwa_lib
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: u_shaped_lib.lwa_ushaped
   :members:
   :undoc-members:
   :show-inheritance: 