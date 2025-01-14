import pickle
import faiss
import os
import re
import json

from sentence_transformers import SentenceTransformer
from flair.data import Sentence
from flair.models import SequenceTagger
from ..interaction_handler.msg import Message
from ..retriever.dense_retriever import DenseRetriever

class QueryClassification:
	"""
	QueryClassification is a class that detects user intent.
	Given the user message, it classifies the user intent as either a question, rejection, or acceptance.

		Args:
			params(dict): A dict of parameters.
	"""
	def __init__(self, params):
		
		self.params = params

		#Question list
		self.ques_list = ["Who will be participating in the session or workshop", #0
						"What authors are in the session or workshop", #1
						"Will author be in the session or workshop", #2
						"What session or workshop will author be in", #3
						"Recommend a session or workshop related to", #4
						"Recommend a session or workshop author is in and related to", #5
						"What papers does the session cover", #6
						"Recommend a session related to author's works", #7
						"What are some sessions related to author's works", #8
						"What are accepted papers in the session", #9
						"What are some papers about in the session", #10
						"Papers related to", #11
						"What are some papers about", #12
						"Give me papers made by", #13
						"Papers written by"] #14

		#Rejection and acceptance keywords
		self.other_intents = {
			'reject': ["Something else", "Anything else", "Not this", "Another one"],
			'acceptance': ["Give me more about", "Give me more like this paper"]
		}

		#Entites refers to what medium the user requests for (paper, session, workshop)
		self.entities = [['paper',  'article'], ['session'], ['workshop'], ['tutorial']]

		#List of all main conferences the chatbot can support
		self.conference_list = ['SIGIR']
		self.conference_years = {'2021': ['2021', '21']}

		self.model = SentenceTransformer('multi-qa-mpnet-base-dot-v1')
		self.tagger = SequenceTagger.load("flair/ner-english-large")

		self.dense_index = DenseRetriever(self.model)
		if os.path.exists('{}/ques_index.pkl'.format(params['index path'])):
			self.dense_index.load_index('{}/ques_index.pkl'.format(params['index path']))
		else:
			self.dense_index.create_index_from_documents(self.ques_list)
			self.dense_index.save_index(index_path='{}/ques_index.pkl'.format(params['index path']), vectors_path='{}/ques_vectors.pkl'.format(params['index path']))
	
	def find_word(self, q, pattern):
		"""
		Checks if a given str contains specified pattern.

		Args:
			q(str): Input string to search on.
			pattern(str): Input string to look for in q.
		
		Returns:
			A match object is q contains pattern, else None.
		"""
		return re.search(pattern, q, flags=re.IGNORECASE)
	
	def check_other_intents(self, conv_list, intent): #'reject' or 'acceptance'
		"""
		Helper function to checks if usery query has intent of non-question type.

		Args:
			conv_list(list): List of interaction_handler.msg.Message, each corresponding to a conversational message from / to the
            user. This list is in reverse order, meaning that the first elements is the last interaction made by user.
			intent(str): Either 'reject' or 'acceptance'. The specified intent to look for in user query.
		
		Returns:
			intent if find_word() is not None, else None.
		"""
		for pattern in self.other_intents[intent]:
			if self.find_word(conv_list[0].text, pattern) is not None:
				return intent
		return None
	
	
	def chack_main_intent(self, conv_list):
		"""
		Checks user intent.

		Args:
			conv_list(list): List of interaction_handler.msg.Message, each corresponding to a conversational message from / to the
            user. This list is in reverse order, meaning that the first elements is the last interaction made by user.
		
		Returns:
			A dict containing the intent ('reject', 'acceptance', 'question'), and the intent index (default=-1 if intent is non-question
			type, for question intent it is the index of the most similar question).
		"""
		if len(conv_list) > 0:
			if self.check_other_intents(conv_list, 'reject') is not None:
				return {'intent': 'reject', 'intent index': -1}
			if self.check_other_intents(conv_list, 'acceptance') is not None:
				return {'intent': 'acceptance', 'intent index': -1}
		
		dense_results = self.dense_index.search([conv_list[0].text])[0]
		dense_results = [i[0] for i in dense_results]
		return {'intent': 'question', 'intent index': dense_results[0]}

	def main_conference(self, conv_list):
		"""
		Checks if user referred to a conference.

		Args:
			conv_list(list): List of interaction_handler.msg.Message, each corresponding to a conversational message from / to the
            user. This list is in reverse order, meaning that the first elements is the last interaction made by user.
		
		Returns:
			A str of the mentioned conference, else '' if user did not mention a conference.
		"""
		result = {'conference': None,
				  'year': None}
		for conference in self.conference_list:
			if self.find_word(conv_list[0].text, conference) is not None:
				result['conference'] = conference
		if result['conference'] is not None:
			for year, lst in self.conference_years.items():
				for word in lst:
					if self.find_word(conv_list[0].text, word) is not None:
						result['year'] = year
						return result
		if len(self.params['DA list']) > 0 and result['conference'] is None and self.params['DA list'][0]['main conference']['conference'] is not None:
			result['conference'] = self.params['DA list'][0]['main conference']['conference']
		
		if len(self.params['DA list']) > 0 and result['year'] is None and self.params['DA list'][0]['main conference']['year'] is not None:
			result['year'] = self.params['DA list'][0]['main conference']['year']
		return result
	
	def entity_keywords(self, conv_list):
		"""
		Checks if user referred to an entity.

		Args:
			conv_list(list): List of interaction_handler.msg.Message, each corresponding to a conversational message from / to the
            user. This list is in reverse order, meaning that the first elements is the last interaction made by user.
		
		Returns:
			A str of the mentioned entity, else '' if user did not mention an entity.
		"""
		result = []
		for entity in self.entities:
			for word in entity:
				if self.find_word(conv_list[0].text, word) is not None:
					result.append(word)
					break
		if len(result) == 0 and len(self.params['DA list'][0]) > 0 and len(self.params['DA list'][0]['entity']) > 0:
			result = self.params['DA list'][0]['entity']
		return result
	
	def get_authors(self, conv_list):
		"""
		Checks if user referred to an author(s).

		Args:
			conv_list(list): List of interaction_handler.msg.Message, each corresponding to a conversational message from / to the
            user. This list is in reverse order, meaning that the first elements is the last interaction made by user.
		
		Returns:
			A str list containing authors that the user mentioned, if any.
		"""
		authors = []
		sentence = Sentence(conv_list[0].text)
		self.tagger.predict(sentence)
		for entity in sentence.get_spans('ner'):
			if entity.get_label("ner").value == "PER":
				authors.append(entity.text)
		return authors
	
	def create_DA(self, conv_list):
		"""
		Creates a DialogueAct based on user query to contain all needed information for dispatchment. 

		Args:
			conv_list(list): List of interaction_handler.msg.Message, each corresponding to a conversational message from / to the
            user. This list is in reverse order, meaning that the first elements is the last interaction made by user.
		
		Returns:
			A DialogueAct.
		"""
		last_DA = None
		last_similarity = 0
		intent_dict = None
		conference = None
		entity = None
		authors = None
		flag = True
		if len(self.params['DA list']) > 0 and self.params['DA list'][0]['flag'] and (self.params['DA list'][0]['index'] in range (7,9) or self.params['DA list'][0]['index'] in range (13,15)):
			last_DA = self.params['DA list'][0]
			intent_dict = {'intent': 'question', 'intent index': self.params['DA list'][0]['index']}
			conference = self.params['DA list'][0]['main conference']
			entity = self.params['DA list'][0]['entity']
			authors = self.params['DA list'][0]['authors']
			flag = False
		else:
			intent_dict = self.chack_main_intent(conv_list)
			if intent_dict['intent'] == 'acceptance':
				last_similarity = self.params['DA list'][1]['last similarity'] + 1

			conference = self.main_conference(conv_list)
			entity = self.entity_keywords(conv_list)
			authors = self.get_authors(conv_list)
		return {'intent': intent_dict['intent'],
				'index': intent_dict['intent index'],
				'main conference': conference,
				'entity': entity,
				'authors': authors,
				'last similarity': last_similarity,
				'error str': None,
				'last DA': last_DA,
				'flag': flag}