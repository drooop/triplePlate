
REM cd d:

echo "Start Process"


set /p keyboardinput="Hit enter to webserver for hermleC"
start /MIN run_webserver_hermleC
echo "done"


set /p keyboardinput="Hit enter to start runCsZMQ for hermleC"
start /MIN runCsZMQ_hermleC
echo "done"


set /p keyboardinput="Hit enter to start web2py for hermleC"
start /MIN 1yunhailiu_hermleC
echo "done"


set /p keyboardinput="Hit enter to start hermleServer for hermleC"
start /MIN 2HermleServer.bat
echo "done"


set /p keyboardinput="Hit enter to start hermleFlow for hermleC"
start /MIN 3HermleCflow.bat
echo "done"
