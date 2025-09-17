# Structure

```plaintext
src
├── app
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
├── kafka_consumer
│   ├── consumer.py
│   ├── requirements.txt
│   └── Dockerfile
├── <topic>_producer_1
.
.
.
├── <topic>_producer_n
│   ├── producer.py
│   ├── requirements.txt
│   └── Dockerfile
├── mongo_init
│   ├── init.py
│   ├── requirements.txt
│   └── Dockerfile
└── docker-compose.yml
```

## Goal
Goal is to start docker and the mongodb is filled with previously gathered init data (mongo_init). For all the data which should be produced by kafka (long time analysis) create a new producer and adjust the consumer.
I suggest to create for each kafka topic an own dedicated collection in the db. Also for each webcrawler one collection. 

### Webcrawler
Webcrawlers can be our notebooks and the goal for each notebook should be to save the gathered data as json file for the init process of our webapp.

### MongoDB
I suggest to just simply use the mongo community server image and add it to our docker setup. If we want to persist our data also after the docker shutsdown we have to mount a volume to it but I think the easiest way would be to start with a fresh new db at each startup.
