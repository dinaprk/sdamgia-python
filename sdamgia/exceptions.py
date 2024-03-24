class IncorrectGiaTypeError(Exception):
    def __init__(self, gia_type):
        print('gia_type can be "oge" or "ege", not %s' % gia_type)


class ProbBlockIsNoneError(Exception):
    def __init__(self):
        print("prob_block is None")
