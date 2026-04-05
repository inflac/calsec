# Contribute
First off, thanks for taking the time to contribute!


## Setup Development Enviroment
The following steps will explain how to setup your development environment to easily develop and contribute to the CalSec project.

1. Clone the Repository
2. Create a virtual python environment called `.venv` inside the project folder.
    
    ```bash
    python3 -m venv .venv
    ```

3. Install the python requirements using pip
    ```bash
    pip3 install -r requirements.txt 
    ```

4. Optional: Install pandoc
The "Build & Package" task uses pandoc to convert the README.md into a .html file which is then put into the created .zip.
When using the task without pandoc being installed, README.md will be included in the .zip.
