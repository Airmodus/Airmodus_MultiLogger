@echo off
setlocal enabledelayedexpansion
goto :main

:create_folder
	echo Creating folder...
	:: store current date and time to variables
	for /f "tokens=1-3 delims=/" %%a in ( "!date!" ) do (
		:: date format: YYYYMMDD
		set current_date=%%c%%b%%a
		echo Date: !current_date!
	)
	for /f "tokens=1-3 delims=.," %%a in ( "!time!" ) do (
		:: time format: HHMMSS
		set current_time=%%a%%b%%c
		echo Time: !current_time!
	)
	:: check if app.py exists
	if not exist ..\src\app.py (
		echo Error: app.py not found.
		goto :eof
	)
	:: get version number from app.py, store to !version_number! variable
	for /f "tokens=3" %%a in ( 'findstr /c:"version_number = " ..\src\app.py' ) do (
		set version_number=%%a
		:: remove quotes around version number
		set version_number=!version_number:~1,-1!
		echo Version: !version_number!
	)
	:: name folder with current date, time and version number
	:: name format: YYYYMMDD-HHMMSS-X.X.X
	set folder_name=!current_date!-!current_time!-!version_number!
	mkdir !folder_name!
	echo Folder \!folder_name!\ created.
	echo.
goto :eof

:copy_files
	:: copy relevant files to build folder
	echo Copying relevant files to \!folder_name!\...
	robocopy ..\src\ !folder_name! app.py style.css /ndl /njh /njs /np /ns /nc
	if %ERRORLEVEL% NEQ 1 goto :eof
	robocopy ..\res !folder_name!\res /E /ndl /njh /njs /np /ns /nc
	if %ERRORLEVEL% NEQ 1 goto :eof
	echo Files copied.
	echo.
goto :eof

:activate_env
	echo Activating conda environment...
	call %USERPROFILE%\anaconda3\Scripts\activate.bat
	:: activate multilogger-env, or create the environment if it doesn't exist
	call conda activate multilogger-env || goto :create_env
	echo Environment multilogger-env activated.
	echo.
goto :eof

:create_env
	:: if there's no multilogger-env, create it using .yaml file
	echo Creating environment...
	call conda env create -f ..\environment.yaml
	:: activate the environment
	call conda activate multilogger-env
	echo Environment multilogger-env created and activated.
	echo.
goto :eof

:build_exe
	echo Building executable...
	echo.
	:: navigate to build folder and run pyinstaller prompt
	cd !folder_name!
	call pyinstaller --name "Airmodus_MultiLogger_!version_number!" --onefile --windowed --add-data="style.css;." --add-data="res;res" app.py
	call conda deactivate
	echo.
	echo Executable built successfully.
	echo.
	echo EXE location:
	echo \!folder_name!\dist\Airmodus_MultiLogger_!version_number!.exe
	echo.
goto :eof

:: if an error occurs, stop script
:error_occurred
	echo.
	echo Error occurred, ending script.
	echo.
	pause
	endlocal
	exit /b
goto :eof

:main
	call :create_folder
	if not exist !folder_name! goto :error_occurred
	call :copy_files
	if %ERRORLEVEL% NEQ 1 goto :error_occurred
	call :activate_env
	call :build_exe
	pause
goto :eof

endlocal