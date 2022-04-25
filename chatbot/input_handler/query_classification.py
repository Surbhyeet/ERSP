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
from flask import request, Flask, jsonify
from flask_cors import CORS

class QueryClassification:
	"""
	QueryClassification is a class that detects user intent.
	Given the user message, it classifies the user intent as either a question, rejection, or acceptance.

		Args:
			params(dict): A dict of parameters.
	"""
	def __init__(self, params):
		
		self.params = params

		#Setting up FLASK
		self.app = Flask(__name__)
		CORS(self.app)

		#Question list
		self.ques_list = ["Who will be participating in the session or workshop", #0
						"What authors are in the session or workshop", #1
						"Will this author be in the session or workshop", #2
						"What session or workshop will this author be in", #3
						"Recommend a session or workshop related to", #4
						"Recommend a session or workshop author is in and related to", #5
						"What papers does the session cover", #6
						"Recommend a session related to this author's works", #7
						"What are some sessions related to this author's works", #8
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
			print("true") #testing purposes
			self.dense_index.load_index('{}/ques_index.pkl'.format(params['index path']))
		else:
			print("false") #testing purposes
			self.dense_index.create_index_from_documents(self.ques_list)
			self.dense_index.save_index(index_path='{}/ques_index.pkl'.format(params['index path']), vectors_path='{}/ques_vectors.pkl'.format(params['index path']))
	
	#Testing purposes
	def serve(self, port=80):
		self.build_endpoints()
		self.app.run(host='0.0.0.0', port=port)
	
	#Testing purposes
	def build_endpoints(self):
		@self.app.route('/encode', methods=['POST', 'GET'])
		def encode_endpoint():
			text = str(request.args.get('text'))
			self.conv_list.insert(0, text)
			da = self.create_DA(self.conv_list)
			bestq = ''
			if da['intent'] == 'rejection':
				bestq = self.other_intents['reject'][0]
			elif da['intent'] == 'acceptance':
				bestq = self.other_intents['acceptance'][0]
			else:
				bestq = self.ques_list[da['index']]
			temp = "intent: " + da['intent'] + ", best question: " + bestq
			results = json.dumps(temp, indent=4)
			return results
	
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
			if self.find_word(conv_list[0], pattern) is not None:
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
		
		dense_results = self.dense_index.search([conv_list[0]])[0]
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
			if self.find_word(conv_list[0], conference) is not None:
				result['conference'] = conference
		if result['conference'] is not None:
			for year, lst in self.conference_years.items():
				for word in lst:
					if self.find_word(conv_list[0], word) is not None:
						result['year'] = year
						return result
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
				if self.find_word(conv_list[0], word) is not None:
					result.append(word)
					break
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
		sentence = Sentence(conv_list[0])
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
	
if __name__ == "__main__": #TESTING PURPOSES
	#conv_list = ["Is Catherine Qi going to be at SIGIR?"]
	params = {'index path': 'D:/ERSP/chatbot/input_handler'}
	q = QueryClassification(params)
	#da = q.create_DA(q.conv_list)
	#print(da['intent'])
	#print(da['main conference']['conference'])
	#print(da['main conference']['year'])
	#print(da['entity'])
	#for a in da['authors']:
	#	print(a)
	#q.serve(9000)