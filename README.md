# TexPrax
### Lorenz Stangier`*`, Ji-Ung Lee`*`, Yuxi Wang, Marvin Müller, Nicholas Frick, Joachim Metternich, and Iryna Gurevych
#### [UKP Lab, TU Darmstadt](https://www.informatik.tu-darmstadt.de/ukp/ukp_home/index.en.jsp)
#### [PTW, TU Darmstadt](https://www.ptw.tu-darmstadt.de/institut_ptw/index.de.jsp)
`*` Both authors contributed equally.

> Drop us a line or report an issue if something is broken (and shouldn't be) or if you have any questions.

* **Contact** 
    * Ji-Ung Lee (lee@ukp.informatik.tu-darmstadt.de) 
    * UKP Lab: http://www.ukp.tu-darmstadt.de/
    * PTW: https://www.ptw.tu-darmstadt.de/
    * TU Darmstadt: http://www.tu-darmstadt.de/

> For license information, please see the LICENSE and README files.

Code for the [TexPrax](https://texprax.de/) project consisting of three components:

* synapserecording
* recorder-bot
* texpraxconnector

A detailed description and installation instructions can be found in the respective folders.

A demo video of the project can be found [here](https://nextcloud.ukp.informatik.tu-darmstadt.de/index.php/s/EcQxDwAEeNT4w8n).

> Disclaimer: This repository contains experimental software and is published for the sole purpose of giving additional background details on the respective publication. 

## Citing the paper (to appear)

```
@article{stangier2022texprax,
  title={TexPrax: A Messaging Application for Ethical, Real-time Data Collection and Annotation},
  author={Stangier, Lorenz and Lee, Ji-Ung and Wang, Yuxi and M{\"u}ller, Marvin and Frick, Nicholas and Metternich, Joachim and Gurevych, Iryna},
  journal={The 2nd Conference of the Asia-Pacific Chapter of the Association for Computational Linguistics and the 12th International Joint Conference on Natural Language Processing (AACL-ICJNLP): System Demonstrations},
  year={2022}
}

```

## Data

An anoymized version of the collected data including annotations can be downloaded from [tudatalib](https://tudatalib.ulb.tu-darmstadt.de/handle/tudatalib/3534) or via [huggingface-datasets](https://huggingface.co/datasets/UKPLab/TexPrax) (CC-by-NC). 

### Synapserecording

The modified Synapse instance to automatically invite the bot into newly created rooms.


### Recorder Bot

The chatbot that keeps track of messages, provides label suggestions, and collects feedback via reactions.

### Texprax Connector

Example code to exchange data with an external dashboard via HTTP requests. 

## How to setup TexPrax

Detailed instructions on how to setup the TexPrax messaging and recording system.

### Setting up Synapse

Clone the repostiory

```git clone https://github.com/UKPLab/TexPrax.git```


Setup your python environment

```
conda create --name=texprax-demo python=3.10
conda activate texprax-demo
```

<small>Note: Due to dependicies on ```collections``` and 
</small>

Install the synapse server first. In your cloned repository, go to synapserecording:
```
cd synapserecording
```
and install the respective code:
```
python setup.py install
```
Now we need to create a config file via:
```
python -m synapse.app.homeserver -c homeserver.yaml --generate-config --server-name=<server-name> --report-stats=<yes|no>
```
<small>Note: If you encounter the error ```AttributeError: module 'jinja2' has no attribute 'Markup'``` , running a different jinja version can help ```pip install Jinja2==3.0.3```
</small>

This has now created a ```homeserver.yaml``` file. Now you can start the homeserver via ```synctl start``` . 
You can check if the installation is running by going to [http://localhost:8008](http://localhost:8008) in your browser.
For further steps, we ask you to follow the instructions in the [official synapse documentation](https://github.com/UKPLab/TexPrax/blob/main/synapserecording/INSTALL.md#setting-up-synapse).

### Debugging and Testing

1. Go to your ```homeserver.yaml``` location.
2. Add a new user via
    
    ```
    register_new_matrix_user -c homeserver.yaml http://localhost:8008
    ```
    
    <small>Note: Make sure that you are in the correct python environment e.g., ```conda activate texprax-demo```
    </small>

3. Go to [Element](https://app.element.io/)
4. Go to Sign In, and ```Edit``` the homeserver from [matrix.org](matrix.org) to [http://localhost:8008](http://localhost:8008) 
5. Sign in with your credentials


### Setting up the recorder bot

Install OLM via

```
sudo apt install libolm-dev
```
or 

```
git clone https://gitlab.matrix.org/matrix-org/olm.git olm
cd olm
cmake . -Bbuild
make
```

Now go to the recorder-bot folder: 

```cd recorder-bot``` 

and install the requirements: 
```pip install -r requirements.txt``` .

<small>Note: Make sure that you are in the correct python environment e.g., ```conda activate texprax-demo```
</small>

Now we need to create a config file with the respective paths etc. You can use ```sample.config.yaml``` as your base file.

We also need to add a new account for the bot (follow the steps above to create a new account). 

As an example, we will use the username ```bot``` with the password ```bot```. 

To add the bot (in the local setup above) we need to modify the ```config.yaml```:

    user_id: "@bot:texprax-demo"
    user_password: "bot"
    homeserver_url: "http://localhost:8008"



The default storeage location of your messages will be ```./store``` . 

You will also have to supply a ```message_path``` (line 34 in ```config.yaml```):

    message_path: "/messages"


Finally, run the bot via:

```
LD_LIBRARY_PATH=<path-to-olm>/olm/build/ <path-to-your-env>/python autorecorderbot_start
```

#### Using PostgreSQL

Setting up postgreSQL is a bit more tricky (the default uses sqlite).
We recommend to follow the [official documentation](https://github.com/UKPLab/TexPrax/blob/main/synapserecording/docs/postgres.md).
Some more detailed instructions are found below.

```
sudo apt install postgresql
```
and check if the respective database user was created. The following command should list all existing users on your system. 

```cut -d: -f1 /etc/passwd```

 Makse sure that the user ```postgres``` is there.
 
 Now we can create a synapse user with:
 
 ```
 sudo -u postgres bash
 createuser --pwprompt synapse_user
 ```

Now (still as the postgres user) run postgresql via ```psql``` and create a database:

```
CREATE DATABASE synapse
 ENCODING 'UTF8'
 LC_COLLATE='C'
 LC_CTYPE='C'
 template=template0
 OWNER synapse_user;
```
Then exit postgresql via ```\q``` and exit the postgres user ```exit``` . Now we the new user to postgresql:
```
sudo vi /etc/postgresql/<your-version-of-postgresql>/main/pg_hbd.conf
```

and add (replace ```trust``` with ```md5``` if you setup a password for the synapse user).
```
host    synapse     synapse_user    ::1/128     trust  
```
before
```
host    all         all             ::1/128     ident
```

