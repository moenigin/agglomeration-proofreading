set root=C:\Utilities\Anaconda

call %root%\Scripts\activate.bat %root%

call conda activate apr

REM cd path to agglomeration-proofreading tool

python run_proofreading.py -dir_path C:\Data\EM\NeuronReconstruction

pause


