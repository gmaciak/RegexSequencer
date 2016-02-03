import sys, os
import string, re

sys.path.append(os.path.dirname(__file__))
from kk_plugin_command_base_v1_1 import *

class TokensMap(CaseInsensitiveDict):
	def __missing__(self, key):
		return "${{{}}}".format(key)

class RegexSequencerCommand(BasePluginCommand):
	"""docstring for ClassName"""
	
	def run(self, edit, **kvargs):
		self.tokens = TokensMap()

		allContentRegion = sublime.Region(0, self.view.size())
		if not allContentRegion.empty():
			try:
				arguments = CaseInsensitiveDict(kvargs)
				if arguments["REGEX_SEQUENCE"] != None:
					regexSequenceJSON = arguments
				else:
					# full path
					path = "{}/{}".format(os.path.dirname(__file__),"sample_regex_sequence.json")
					sequenceView = sublime.active_window().open_file(path,0)
					sequenceRegion = sublime.Region(0, sequenceView.size())
					jsonString = sequenceView.substr(sequenceRegion)
				
					# decode json
					regexSequenceJSON = sublime.decode_value(jsonString)
					regexSequenceJSON = CaseInsensitiveDict(regexSequenceJSON)

				if type(regexSequenceJSON) is list:
					masterSequence = regexSequenceJSON
				else:
					masterSequence = regexSequenceJSON["REGEX_SEQUENCE"]

				# find patterns global definitions
				self.regularExpressions = regexSequenceJSON["REGULAR_EXPRESSIONS"]
				if self.regularExpressions == None:
					self.regularExpressions = dict();

				# replace patterns global definitions
				self.replaceTemplates = regexSequenceJSON["REPLACE_TEMPLATES"]
				if self.replaceTemplates == None:
					self.replaceTemplates = dict();

				# debug option
				shouldCommentSteps = regexSequenceJSON["DEBUG"]
				self.debug = shouldCommentSteps if shouldCommentSteps != None else False

				# output string, generated only if comments for each step is enabled
				self.output = "" if self.debug else None
				self.stepIndex = 0
				source = self.view.substr(sublime.Region(0, self.view.size()))

				# run master sequence
				self.run_sequence(edit,masterSequence,regexSequenceJSON)

				# if output string available replace all content with it
				# print("self.output: ",self.output)
				if self.output != None:
					comment = str()
					# log available global regular expressions
					comment += "// GLOBAL REGEXES:\n"
					for key in self.regularExpressions:
						comment += "//    \"{}\" = \"{}\"\n".format(key,self.regularExpressions[key])

					# log available global replace templates
					comment += "// GLOBAL REPLACES:\n"
					for key in self.replaceTemplates:
						comment += "//    \"{}\" = \"{}\"\n".format(key,self.replaceTemplates[key])
					
					# put log before the output
					self.output = "{}\n\n{}".format(comment,self.output)

					# insert soruce text at the begining of the output
					self.output = "{}\n\n{}".format(source,self.output)

					# replace content with output
					allContentRegion = sublime.Region(0, self.view.size())
					self.view.replace(edit, allContentRegion, self.output)
					
			except Exception as ex:
				self.show_exception()
				raise ex

	def run_sequence(self, edit, sequence, json={}):
		if type(sequence) is list:
			for step in sequence:
				if type(step) is str:
					sequence = json[step]
					self.run_sequence(edit,sequence,json)
				elif type(step) is dict:
					step = CaseInsensitiveDict(step)
					self.handle_step(edit,step)
				else:
					print("ERROR: run_sequence(self, edit, sequence, json={}): invalid step type in sequence: ",sequence)
		else:
			print("ERROR: run_sequence(self, edit, sequence, json={}): sequence is not a list!")

	def handle_step(self, edit, step):
		self.stepIndex += 1
		if self.output != None:
			self.output += "// STEP: {0}\n".format(self.stepIndex)
		findAll = step["FIND_ALL"]
		find = step["FIND"]
		replace = step["REPLACE"]
		self.updateTokens(step["TOKENS"])
		if findAll != None:
			self.handle_find_all(edit, findAll)
		if replace != None:
			self.handle_replace(edit, step)
		elif find != None:
			self.handle_find_all(edit, find)

	def updateTokens(self,tokens):
		if type(tokens) is dict:
			if self.output != None:
				self.output += "// Available TOKENS:\n"
			for token in tokens:
				find = tokens[token]
				matches = list()
				regions = self.view.find_all(find,0,"$1",matches)
				if len(matches) > 0 and len(matches[0]) > 0:
					self.tokens[token] = matches[0]
				elif len(regions) > 0:
					self.tokens[token] = self.view.substr(regions[0])
				else:
					self.tokens[token] = str()
			if self.output != None:
				for token in sorted(list(self.tokens.keys())):
					self.output += "//    \"{}\" = \"{}\"\n".format(token,self.tokens[token])

	def handle_find_all(self,edit,find):
		# if find pattern is a key for known global pattern
		if find in self.regularExpressions:
			find = self.regularExpressions[find];

		regions = self.view.find_all(find)
		if len(regions) > 0:
			lines = list()
			allContentRegion = sublime.Region(0, self.view.size())
			
			# get all not selected regions
			for region in regions:
				if not region.empty():
					lines.append(self.view.substr(region))

			text = "\n".join(lines);
			self.view.replace(edit, allContentRegion, text)

			if self.output != None:
				self.output += "// FIND ALL: \"{0}\"\n".format(find)
				self.output += "{0}\n\n".format(text)

	def replace(self,find,replace,outputData):
		# if find pattern is a key for known global pattern
		if find in self.regularExpressions:
			find = self.regularExpressions[find];

		# if replace is a key for known global template
		if replace in self.replaceTemplates:
			replace = self.replaceTemplates[replace];

		# get final replace template by replacing tokens with its values
		replace = string.Template(replace).safe_substitute(self.tokens)

		# find regions to replace and apply the template
		# source: https://forum.sublimetext.com/t/view-replace-regex/8566/3
		replacements = list()
		regions = self.view.find_all(find, 0, replace, replacements)

		# update output data
		outputData[replace] = {"regions": regions, "replacements" : replacements}

	def handle_replace(self,edit,step):
		findAll = step["FIND_ALL"]
		find = step["FIND"]
		if find == None: find = findAll

		# 'replace' may be a single PERL-like pattern or a list of patterns.
		#	Nice overview about Named Capturing Groups:
		#		http://www.regular-expressions.info/named.html
		# Sublime Text uses the Perl Compatible Regular Expressions (PCRE) engine
		#	source: http://docs.sublimetext.info/en/latest/search_and_replace/search_and_replace_overview.html
		replace = step["REPLACE"]

		replaceTemplates = dict()
		if replace != None:
			if type(replace) is list:
				for pattern in replace:
					self.replace(find,pattern,replaceTemplates)
			else:
				self.replace(find,replace,replaceTemplates)

			if self.output != None:
				self.output += "// FIND: \"{0}\"\n".format(find)
			
			source = self.view.substr(sublime.Region(0, self.view.size()))
			result = str()
			for pattern in replaceTemplates:

				data = replaceTemplates[pattern]
				regions = data["regions"]

				if self.output != None:
					self.output += "// REPLACE: \"{0}\"\n".format(pattern)
					
				if len(regions) > 0:
					replacements = data["replacements"]
					if type(pattern) is str:

						# reverse replacements to avoid invalidations
						# of the regions during changing the buffer
						regions.reverse()
						replacements.reverse()

						# replace text in regions with new values
						for region, repl in zip(regions, replacements):
							self.view.replace(edit, region, repl)

						if self.output != None:
							# add result of the proccess to the output
							self.output += "{0}\n\n".format(self.view.substr(sublime.Region(0, self.view.size())))
						
						# update result (output string for all replacements)
						result += "{0}\n\n".format(self.view.substr(sublime.Region(0, self.view.size())))

						# restore previous content for next replace operation
						allContentRegion = sublime.Region(0, self.view.size())
						self.view.replace(edit, allContentRegion, source)
			
			# load result
			allContentRegion = sublime.Region(0, self.view.size())
			self.view.replace(edit, allContentRegion, result)