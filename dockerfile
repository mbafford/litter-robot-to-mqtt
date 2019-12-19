FROM python:3

ADD litter-robot-intercept.py /
ADD requirements.txt / 

RUN pip install -r /requirements.txt

CMD [ "python", "litter-robot-intercept.py", "/litter-robot/intercept.log" ]
