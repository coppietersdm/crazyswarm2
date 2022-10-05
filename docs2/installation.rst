.. _installation:

Installation
============

Crazyswarm2 runs on **Ubuntu Linux** in one of the following configurations:

====== ======== ========
Ubuntu Python   ROS2
------ -------- --------
20.04  3.7, 3.8 Galactic
====== ======== ========

.. warning::
   The `Windows Subsystem for Linux (WSL) <https://docs.microsoft.com/en-us/windows/wsl/about>`_ is experimentally supported but you'll have to use `usbipd-win <https://github.com/dorssel/usbipd-win/>`_.
   This program will link the crazyradio directly with WS, but beware of bugs. Check out their `WSL connect guide <https://github.com/dorssel/usbipd-win/wiki/WSL-support/>`_.

.. warning::
   Avoid using a virtual machine if possible: they add additional latency and might cause issues with the visualization tools.

First Installation
------------------

1. If needed, install ROS2 using the instructions at https://docs.ros.org/en/galactic/Installation.html.

2. Install dependencies

    .. code-block:: bash

        sudo apt install libboost-program-options-dev libusb-1.0-0-dev

3. Set up your ROS2 workspace

    .. code-block:: bash

        mkdir -p ros2_ws/src
        cd ros2_ws/src
        git clone https://github.com/IMRCLab/crazyswarm2 --recursive
        git clone --branch ros2 --recursive https://github.com/IMRCLab/motion_capture_tracking.git

4. Build your ROS2 workspace

    .. code-block:: bash

        cd ../
        colcon build --symlink-install

    .. note::
       symlink-install allows you to edit Python and config files without running `colcon build` every time.

5. Set up software-in-the-loop simulation

    .. code-block:: bash

        cd crazyflie_py/crazyflie_py/cfsim
        CSW_PYTHON=python3 make


Updating
--------

You can update your local copy using the following commands:

.. code-block:: bash

    cd ros2_ws/src/crazyswarm2
    git pull
    git submodule sync
    git submodule update --init --recursive
    cd ../
    colcon build --symlink-install


.. Once you have completed installation,
.. move on to the :ref:`configuration` section and configure Crazyswarm for your hardware.