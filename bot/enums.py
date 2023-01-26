from enum import IntEnum


class JobStatus(IntEnum):
    CENSORED = -2
    FAULTED = -1
    INIT = 0
    WORKING = 2
    FINALIZING = 3
    DONE = 4
