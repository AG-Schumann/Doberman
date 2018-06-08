#! /usr/bin/env python3.3


class supervisionProtocol(object):
    """
    Class that holds the supervision protcoll
    c: Client, s: server
    procoll structure:
    s: waiting for request
    c: opening connection
    c: (sending number as request)1
    s: A
    c: reading
    s: ((request code):(status of request code)) 1:1
    c: reading
    s: closes connection
    c: evaluating answer
    c: closing connection
    c: writing answer in slowcontrol log
    
    finally the client slowcontrol might react basing on value range

    currently implemented requests:
    1: online status
        answers: 1, 0
    2: is there a warning
        1, 0, now static:2
    3: is there an alarm
        1, 0, now static:3

    the answers and reactions are define in the answer_(request code)


    Basically a answer/ request structure has to look like:
    1) add request code to self.__qaa: self.__qaa.append(Y)

    2) write functions like:
    
    def answer_Y(self):
        if status:
            reaction = 1
        elif status is None:
            reaction = -1
        else:
            reaction = 0
        return reaction

    def querry_online(self):
        '''query remote slow control'''
        return self.send(Y)
    def status_online(self):
        '''query own slow control'''
        return self.reply(Y)

    """
    def __init__(self):
        self.__qaa = list()
# never use 0 or A or \X with X may be anything
        self.__qaa.append(1) # are u online?
        self.__qaa.append(2) # have u a warning?
        self.__qaa.append(3) # do you have an alarm?
        
    def reply(self, question):
        """
        do not modify this to change answer/ reaction, change answer_(code) function. This function maps the answer to a request code
        """
        answer_case = 'answer_' + str(question)
        answer = getattr(self, answer_case, lambda: 0)
        return question+":"+str(answer())

    def check_reply(self, question, answer):
        """
        function checking whether a reply makes sense and fits to the question
        """
        question = str(question)
        answer = str(answer).split(":",2)
        if len(answer) != 2:
            return -2
        if not question in list(map(str, self.__qaa)):
            return -1
        if not question in answer[1]:
            return 0
        return answer[1]

    def answer_1(self):
        return 1
    def querry_online(self):
        return self.send(1)
    def status_online(self):
        return self.reply(1)

    def answer_2(self):
        return 2
        #if there is warning:
        #    return 1
        #else:
        #    return 0
    def querry_warning(self):
        return self.send(2)
    def status_warning(self):
        return self.reply(2)

    def answer_3(self):
        return 3
        #if there is alarm:
        #    return 1
        #else:
        #    return 0
    def querry_alarm(self):
        return self.send(3)
    def status_alarm(self):
        return self.reply(3)

    def send(self, message):
        """
        dummy function, do not modify
        """
        return message
