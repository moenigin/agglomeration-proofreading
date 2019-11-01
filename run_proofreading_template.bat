set root=C:\Utilities\Anaconda

call %root%\Scripts\activate.bat %root%

call conda activate apr

cd C:\Users\moennila\testpck\agglomeration-proofreading

python run_proofreading.py -dir_path C:\Data\EM\NeuronReconstruction

pause


