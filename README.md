# Airmodus MultiLogger
Airmodus MultiLogger is intended for logging, monitoring and controlling various Airmodus devices.

An .exe version of the software can be downloaded from the repository's [Releases](https://github.com/Airmodus/Airmodus_MultiLogger/releases) section.
## Environment setup instructions
### 1. Install Anaconda
The project is being developed using the Anaconda Python distribution. Anaconda's installation instructions can be found [here](https://docs.anaconda.com/anaconda/install/).
### 2. Create a new Anaconda environment
All required [dependencies](#dependencies) are specified in the `environment.yaml` file. To create a new environment from the file, use:
```
conda env create -f environment.yaml
```
The default environment name is `multilogger-env`. To specify a different name, use `-n`:
```
conda env create -f environment.yaml -n env_name
```
### 3. Activate the new environment
Activate the new Anaconda environment using:
```
conda activate multilogger-env
```
If the environment was given a different name, use it instead of `multilogger-env` in the above line.
### 4. Run app.py
To start MultiLogger, navigate to the repository's `src` folder and run `app.py`.
## Dependencies
### External Python packages
- NumPy
- pySerial
- PyQt
- PyQtGraph (version 0.13.3)
### Python Standard Library modules (included with Python)
- time
- datetime
- os
- locale
- platform
- logging
- random
- traceback
- json
- warnings