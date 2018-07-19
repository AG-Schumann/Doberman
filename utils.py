from ast import literal_eval


def getUserInput(text, input_type=None, be_in=None, be_not_in=None, be_array=False, limits=None, string_length=None, exceptions=None):
    """
    Ask for an input bye displaying the 'text'.
    It is asked until:
      the input has the 'input_type(s)' specified,
      the input is in the list 'be_in' (if not None),
      not in the list 'be_not_in' (if not None),
      the input is between the limits (if not None).
      has the right length if it is a string (if not None)
    'input_type', 'be_in' and 'be_not_in' must be lists or None.
    'limits' must be a list of type [lower_limit, higher_limit].
    ' lower_limit' or 'higher_limit' can be None. The limit is <=/>=.
    'string_length' must be a list of [lower_length, higher_length]
    ' lower_length' or 'higher_length' can be None. The limit is <=/>=.
    'be_array' can be True or False, it returns the input as array or not.
    If the input is in the exceptions it is returned without checks.
    """
    while True:
        # Read input.
        try:
            user_input = input_eval(input(text), input_type != [str])
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print("Error: %s. Try again." % e)
            continue
        # Check for input exceptions
        if exceptions:
            if user_input in exceptions:
                return user_input
        # Remove string signs
        if input_type == [str] and isinstance(user_input, str):
            user_input = ''.join(c for c in user_input if c not in ['"',"'"])
        # Transform input to list
        if not be_array:
            user_input = [user_input]
        else:
            if isinstance(user_input, tuple):
                user_input = list(user_input)
            elif isinstance(user_input, str):
                user_input = user_input.split(",")
            elif isinstance(user_input, (int, float)):
                user_input = [user_input]
        # Remove spaces after comma for input lists
        if be_array and input_type == [str]:
            user_input = [item.strip() for item in user_input]
        # Check input for type, be_in, be_not_in, limits.
        if input_type:
            if not all(isinstance(item, tuple(input_type)) for item in user_input):
                print("Wrong input format. Must be in %s. Try again." %
                    str(tuple(input_type)))
                continue
        if be_in:
            if any(item not in be_in for item in user_input):
                print("Input must be in: %s. Try again." % str(be_in))
                continue
        if be_not_in:
            if any(item in be_not_in for item in user_input):
                print("Input is not allowed to be in: %s. Try again." % str(be_not_in))
                continue
        if limits:
            if limits[0] or limits[0] == 0:  # Allows also 0.0 as lower limit
                if any(item < limits[0] for item in user_input):
                    print("Input must be between: %s. Try again." % str(limits))
                    continue
            if limits[1]:
                if any(item > limits[1] for item in user_input):
                    print("Input must be between: %s. Try again." % str(limits))
                    continue
        # Check for string length
        if string_length:
            if string_length[0] != None:
                if any(len(item) < string_length[0] for item in user_input):
                    print("Input string must have more than %s characters."
                        " Try again." % str(string_length[0]))
                    continue
            if string_length[1] != None:
                if any(len(item) > string_length[1] for item in user_input):
                    print("Input string must have less than %s characters."
                        " Try again." % str(string_length[1]))
                    continue
        break
    if not be_array:
        return user_input[0]
    return user_input

def adjustListLength(input_list, length, append_item, input_name=None):
    """
    Appending 'append_item' to the 'input_list'
    until 'length' is reached.
    """
    if len(input_list) < length:
        input_list += [append_item]*(length - len(input_list))
    elif len(input_list) > length:
        input_list = input_list[:length]
    return input_list

def input_eval(inputstr, literaleval=True):
    if not isinstance(inputstr, str):
        return -1
    inputstr = inputstr.strip(' \r\t\n\'"').expandtabs(4)
    if literaleval:
        try:
            return literal_eval(inputstr)
        except:
            pass
    return str(input_str)

