class NerqError(Exception):
    pass

class NerqNotFoundError(NerqError):
    pass

class NerqRateLimitError(NerqError):
    pass

class NerqAuthError(NerqError):
    pass

class NerqTimeoutError(NerqError):
    pass
