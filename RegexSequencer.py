import sublime, sys, os
import string, re

sys.path.append(os.path.dirname(__file__))
from kk_plugin_command_base_v1_1 import *

class TokensMap(CaseInsensitiveDict):
	def __missing__(self, key):
		return "${{{}}}".format(key)

class RegexSequencerCommand(BasePluginCommand):
	
	def run(self, edit, **kvargs):
		allContentRegion = sublime.Region(0, self.view.size())
		if not allContentRegion.empty():

			self.stepIndex = 0
			self.tokens = TokensMap()
			self.patternsOfTokens = CaseInsensitiveDict()

			try:
				arguments = CaseInsensitiveDict(kvargs)
				if arguments["SEQUENCE"] != None:
					self.json = arguments
				else:
					message = "Empty command args dictionary. No sequence attached to regex_sequencer command."
					print(message)
					sublime.status_message(message)
					return
					# TODO: support of using sequence opened in other view
					# full path
					path = "{}/{}".format(os.path.dirname(__file__),"sample_regex_sequence.json")
					sequenceView = sublime.active_window().open_file(path,0)
					sequenceRegion = sublime.Region(0, sequenceView.size())
					jsonString = sequenceView.substr(sequenceRegion)
				
					# decode json
					self.json = sublime.decode_value(jsonString)
					self.json = CaseInsensitiveDict(self.json)

				# debug option
				shouldCommentSteps = self.json["DEBUG"]
				self.debug = shouldCommentSteps if shouldCommentSteps != None else False

				# set active window
				print("active window",
					sublime.active_window().id(),
					sublime.active_window().active_view().name(),
					sublime.active_window().active_view().file_name())

				# Start logging
				if self.debug:
					sublime.log_commands(True)
					sublime.log_result_regex(True)
					sublime.log_input(False)

				# output string, generated only if comments for each step is enabled
				self.output = "" if self.debug else None

				# Load Master Sequence
				if type(self.json) is list:
					masterSequence = self.json
				else:
					masterSequence = self.json["SEQUENCE"]

				# steps global definitions
				self.steps = self.json["STEPS"]
				if self.steps == None:
					self.steps = CaseInsensitiveDict();

				# commands global definitions
				self.commands = self.json["COMMANDS"]
				if self.commands == None:
					self.commands = CaseInsensitiveDict();

				# find patterns global definitions
				self.regularExpressions = self.json["REGULAR_EXPRESSIONS"]
				if self.regularExpressions == None:
					self.regularExpressions = CaseInsensitiveDict();

				# replace patterns global definitions
				self.replaceTemplates = self.json["REPLACE_TEMPLATES"]
				if self.replaceTemplates == None:
					self.replaceTemplates = CaseInsensitiveDict();

				# content of the buffer before the the any sequence start
				source = self.view.substr(sublime.Region(0, self.view.size()))

				# run master sequence
				self.run_sequence(edit,masterSequence)

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

				# End logging
				if self.debug:
					sublime.log_commands(False)
					sublime.log_result_regex(False)
					sublime.log_input(False)
					
			except Exception as ex:
				self.show_exception()
				raise ex

	def updateTokens(self,tokens,flags=0):
		if type(tokens) is dict:
			self.patternsOfTokens.update(tokens)

			if self.output != None:
				self.output += "// Available TOKENS:\n"
			for token in tokens:
				find = tokens[token]
				matches = list()
				regions = self.view.find_all(find,flags,"$1",matches)
				if len(matches) > 0 and len(matches[0]) > 0:
					self.tokens[token] = matches[0]
				elif len(regions) > 0:
					self.tokens[token] = self.view.substr(regions[0])
				else:
					self.tokens[token] = str()
			if self.output != None:
				for token in sorted(list(self.tokens.keys())):
					self.output += "//    \"{}\" = \"{}\" (regex: \"{}\" )\n".format(token,self.tokens[token],self.patternsOfTokens[token])

	def load_replace_desriptors(self,find,replace,outputData,flags=0):
		key = replace
		
		# if find pattern is a key for known global pattern
		find = self.find_pattern_for_key(find)

		# if replace is a key for known global template
		replace = self.replace_template_for_key(replace)

		# get final replace template by replacing tokens with its values
		replace = string.Template(replace).safe_substitute(self.tokens)

		# find regions to replace and apply the template
		# source: https://forum.sublimetext.com/t/view-replace-regex/8566/3
		replacements = list()
		regions = self.view.find_all(find, flags, replace, replacements)

		# update output data
		outputData[key] = {
			"template": replace,
			"regions": regions,
			"replacements" : replacements
		}

	#================================ GETTERS ==================================

	def sequence_for_key(self,key):
		sequence = self.json[key]
		if sequence == None:
			sequence = self.steps[key]
		return sequence

	def find_pattern_for_key(self,pattern):
		# if find pattern is a key for known global pattern
		if pattern in self.regularExpressions:
			return self.regularExpressions[pattern];
		return pattern

	def replace_template_for_key(self,template):
		# if template is a key for known global template
		if template in self.replaceTemplates:
			return self.replaceTemplates[template];
		return template

	#==================== SEQUENCE/REGEX STEP/COMMAND ==========================

	def run_sequence(self, edit, sequence):
		# name of sequence/step/command
		if type(sequence) is str:
			print("sequence/step/command:",sequence)
			sequence = self.sequence_for_key(sequence)
		print(sequence)

		# sequence
		if type(sequence) is list:
			for step in sequence:
				self.run_sequence(edit,step)
		# regex_step/command
		elif type(sequence) is dict:
			step = CaseInsensitiveDict(sequence)
			self.run_step(edit,step)
		else:
			print("ERROR: run_sequence(self, edit, sequence): Sequence node has invalid type: {}",sequence)

	def run_step(self, edit, step):
		if type(step) is str:
			print("Step:",step)
			step = self.sequence_for_key(step)

		# increment step index	
		self.stepIndex += 1

		# search flags
		literalFlag = step["LITERAL"]
		ignoreCaseFlag = step["IGNORECASE"]
		flags = sublime.LITERAL if literalFlag != None and literalFlag else 0
		flags |= sublime.IGNORECASE if ignoreCaseFlag != None and ignoreCaseFlag else 0
		# print("sublime.LITERAL",sublime.LITERAL,"sublime.IGNORECASE",sublime.IGNORECASE)
		# print("flags",flags,"literalFlag",literalFlag,"ignoreCaseFlag",ignoreCaseFlag)

		if self.output != None:
			self.output += "// STEP: {0}\n".format(self.stepIndex)
			self.output += "// Search flags: LITERAL = {}, IGNORECASE = {}\n".format(literalFlag,ignoreCaseFlag)
			
		# load tokens from the step
		self.updateTokens(step["TOKENS"],flags)

		findAll = step["FIND_ALL"]
		find = step["FIND"]

		# 'replace' may be a single PERL-like pattern or a list of patterns.
		#	Nice overview about Named Capturing Groups:
		#		http://www.regular-expressions.info/named.html
		# Sublime Text uses the Perl Compatible Regular Expressions (PCRE) engine
		#	source: http://docs.sublimetext.info/en/latest/search_and_replace/search_and_replace_overview.html
		replace = step["REPLACE"]

		command = step["COMMAND"]

		isUsingFindAll = replace == None
		if find == None:
			find = findAll
			isUsingFindAll = True

		if findAll != None:
			if self.output != None:
				self.output += "// FIND ALL: \"{0}\"\n".format(find)
			self.handle_find_all(edit, findAll, flags)

		if self.output != None:
			findNodeName = "FIND (ALL)" if isUsingFindAll else "FIND"
			self.output += "// {}: \"{}\"\n".format(findNodeName,self.find_pattern_for_key(find))

		if replace != None:
			self.handle_replace(edit, find, replace, flags)
		elif find != None and findAll == None:
			self.handle_find_all(edit, find, flags)

		if command != None:
			self.run_command(command, step["ARGS"])

	def run_command(self,command,args):
		if type(command) is str:
			if self.output != None:
				self.output += "// COMMAND: \"{} {}\"\n".format(command, args if args != None else "")

			if args != None:
				self.view.run_command(command, args)
			else:
				self.view.run_command(command)

	#=============================== HANDLERS ==================================

	def handle_find_all(self,edit,find,flags=0):
		# if find pattern is a key for known global pattern
		find = self.find_pattern_for_key(find)

		regions = self.view.find_all(find,flags)
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
				self.output += "{0}\n\n".format(text)

	def handle_replace(self,edit,find,replace,flags=0):
		if find != None and replace != None:

			# dictionaries which define replacement for each replace key
			replaceDescriptors = dict()

			# replace patterns or its names in order of definitions
			replacementOrder = list()

			if type(replace) is list:
				replacementOrder += replace
				for pattern in replace:
					self.load_replace_desriptors(find,pattern,replaceDescriptors,flags)
			else:
				replacementOrder.append(replace)
				self.load_replace_desriptors(find,replace,replaceDescriptors,flags)
			
			source = self.view.substr(sublime.Region(0, self.view.size()))
			result = str()
			for key in replacementOrder:
				descriptor = replaceDescriptors[key]
				regions = descriptor["regions"]
				replaceTemplate = descriptor["template"]

				if self.output != None:
					self.output += "// REPLACE: \"{0}\"\n".format(replaceTemplate)
					
				if len(regions) > 0:
					replacements = descriptor["replacements"]
					if type(replaceTemplate) is str:

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
			