U-shaped Laser Package
=====================

A Python package for analyzing laser measurements, with a focus on U-shaped laser configurations and linewidth measurements.

Documentation
------------

For detailed documentation, including installation instructions, usage examples, and API reference, visit our `Read the Docs page <https://u-shaped-laser-package.readthedocs.io/>`_.

Overview
--------

This package provides tools for analyzing various laser measurements including:

* Linewidth measurements
* Frequency noise (FN) analysis
* Relative intensity noise (RIN) analysis
* Side Mode Suppression Ratio (SMSR) measurements
* Coherent Self-Heterodyne (CSH) measurements

Installation
------------

.. code-block:: bash

   pip install u-shaped-laser

Package Structure
----------------

The package is organized into several modules:

Core Analysis Modules
~~~~~~~~~~~~~~~~~~~~

* ``zeta_fit_plot.py``: Functions for fitting and plotting zeta functions for linewidth analysis
* ``beta_sep.py``: Implementation of beta separation method for laser linewidth analysis
* ``CSH.py`` & ``CSH_unmodified.py``: Tools for analyzing Coherent Self-Heterodyne measurements
* ``HighFinesse_FN.py``: Analysis tools for High Finesse frequency noise measurements

Data Processing
~~~~~~~~~~~~~~

* ``load_data.py``: Core data loading and processing functionality
* ``data_processing.py``: Additional data processing utilities
* ``file_management_lib.py``: File handling and path management utilities

Analysis Tools
~~~~~~~~~~~~~

* ``fit_functions.py``: Mathematical functions for fitting laser measurement data
* ``lwa_lib.py``: Laser linewidth analysis library
* ``lwa_ushaped.py``: Specific analysis tools for U-shaped laser configurations

Visualization
~~~~~~~~~~~~

* ``smsr_vs_linewidth.py``: Tools for analyzing SMSR vs linewidth relationships
* ``ushaped_agilent_characterization.py``: Characterization tools for Agilent measurements
* ``ushaped_linewidth_vs_feedback.py``: Analysis of linewidth vs feedback relationships
* ``ushaped_smsr.py``: SMSR analysis for U-shaped laser configurations

Key Features
-----------

1. **Linewidth Analysis**

   * Multiple methods for linewidth calculation
   * Support for various measurement techniques
   * Automated data processing and filtering

2. **Noise Analysis**

   * Frequency noise (FN) analysis
   * Relative intensity noise (RIN) analysis
   * Noise floor calculations

3. **Data Visualization**

   * Comprehensive plotting tools
   * Customizable visualization parameters
   * Publication-quality figure generation

4. **Data Processing**

   * Automated data loading and processing
   * Support for multiple file formats
   * Robust error handling

Usage Examples
-------------

Basic Linewidth Analysis
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from u_shaped_lib import zeta_fit_plot

   # Load and analyze linewidth data
   linewidth = zeta_fit_plot.plot_linewidth(path_to_data)

SMSR Analysis
~~~~~~~~~~~~

.. code-block:: python

   from u_shaped_lib import ushaped_smsr

   # Analyze SMSR measurements
   peaks = ushaped_smsr.plot_single(path_to_data, plot=True)

Frequency Noise Analysis
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from u_shaped_lib import lwa_lib

   # Load and analyze frequency noise data
   lwa = lwa_lib.LWA(path_to_data)
   linewidth = lwa.fit_linewidth()

Dependencies
-----------

* numpy
* pandas
* matplotlib
* scipy
* cycler

License
-------

This project is licensed under the MIT License - see the LICENSE file for details.

Authors
-------

* Simon T. Thomsen
* Jeppe H. Surrow

Acknowledgments
--------------

This package was developed as part of research at Aarhus University. 