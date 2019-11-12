# Agglomeration Proofreading Tool

## Installation

Prerequisites:
The proofreading tool needs [chrome](https://www.google.com/chrome/) and ChromeDriver to be installed. For ChromeDriver download and unzip the [ChromeDriver](https://chromedriver.chromium.org/downloads) for your chrome version and include the chrome driver location in your PATH environment variable.

### installation with anaconda:
<details>
  <summary>expand</summary>
  <p>
    
  If necessary download and install [anaconda](https://www.anaconda.com/distribution/).
  Open anaconda prompt and install git:
  ```
  conda install git
  ```
  Create a folder for the proofreading tool and clone the git repository
  ```
  cd <dir_path_to_tool>
  git clone https://github.com/moenigin/agglomeration-proofreading.git
  ```
  navigate to the proofreading folder and install the downloaded environment.yml,
  ```
  cd agglomeration-proofreading
  conda env create -f apr.yml
  ```
  activate the environment and install the remaining requirements
  ```
  conda activate apr
  pip install -r requirements.txt
  ```
  </p>
</details>

### installation with pip:
<details>
  <summary>expand</summary>
  <p>

  It is recommended to work in to create a dedicated environment for the proofreading tool. It requires Python 3.7 and [git](https://git-scm.com/downloads) to be installed.

  ```
  git clone --recurse https://github.com/moenigin/agglomeration-proofreading.git
  ```
  navigate to the agglomeration-proofreading subfolder and install requirements

  ```
  cd agglomeration-proofreading
  pip install -r requirements.txt
  ```
  </p>
</details>


## Usage

To run the proofreading tool type in the prompt

```
python run_proofreading.py
```

The configuration of the proofreading tool can be adapted either through editing the proofreading.ini or by passing arguments directly in the prompt.
For list of arguments see

```
python run_proofreading.py -h
```

for usage instructions see [instructions](/instructions.md)