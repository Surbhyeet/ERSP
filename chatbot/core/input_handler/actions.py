from abc import ABC, abstractmethod
from func_timeout import func_timeout, FunctionTimedOut
import traceback

class Action(ABC):
    @staticmethod
    @abstractmethod
    def run(conv_list, params):
        """
        This is a static method for an abstract class. This method should run the corresponding action.
        Args:
            conv_list(list): List of util.msg.Message, each corresponding to a conversational message from / to the
            user. This list is in reverse order, meaning that the first elements is the last interaction made by user.
            params(dict): A dict containing some mandatory and optional parameters.
        """
        pass

class RetrievalAction(Action):
    @staticmethod
    def run(conv_list, params):
        """
        
        Args:
            conv_list(list): List of util.msg.Message, each corresponding to a conversational message from / to the
            user. This list is in reverse order, meaning that the first elements is the last interaction made by user.
            params(dict): A dict containing some parameters. The parameter 'retrieval' is required, which should be the
            retrieval model object.
        Returns:
            
        """
        index = params['DA list'][0]['index']
        return params['actions']['retrieval'].get_results(conv_list, index)

class ConferenceAction(Action):
    @staticmethod
    def run(conv_list, params):
        """

        Args:
            conv_list(list): List of util.msg.Message, each corresponding to a conversational message from / to the
            user. This list is in reverse order, meaning that the first elements is the last interaction made by user.
            params(dict): A dict containing some parameters. The parameter 'retrieval' is required, which should be the
            retrieval model object.
        Returns:

        """
        index = params['DA list'][0]['index']
        return params['actions']['conference'].get_results(conv_list, index)

class QuestionAction(Action):
    @staticmethod
    def run(conv_list, params):
        """

        Args:
            conv_list(list): List of util.msg.Message, each corresponding to a conversational message from / to the
            user. This list is in reverse order, meaning that the first elements is the last interaction made by user.
            params(dict): A dict containing some parameters. The parameter 'retrieval' is required, which should be the
            retrieval model object.
        Returns:

        """
        return params['actions']['question'].get_results(conv_list)