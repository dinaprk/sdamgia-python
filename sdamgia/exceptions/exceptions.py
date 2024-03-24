class IncorrectGiaTypeException(Exception):
    def __init__(self, gia_type):
        print('gia_type can be "oge" or "ege", not %s' % gia_type)


class ProbBlockIsNoneException(Exception):
    def __init__(self):
        print("prob_block is None")
