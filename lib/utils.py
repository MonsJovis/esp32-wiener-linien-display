
def two_digits(number_or_string):
  if isinstance(number_or_string, str):
    number_or_string = int(number_or_string)

  if number_or_string < 10:
    return "0" + str(number_or_string)

  return str(number_or_string)
