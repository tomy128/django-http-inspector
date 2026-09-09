class CapturingIterable:
    def __init__(self, iterable, capture):
        self.iterable = iterable
        self.iterator = iter(iterable)
        self.capture = capture
        self.finished = False
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            data = next(self.iterator)
            self.capture.observe_response(data)
            return data
        except StopIteration:
            self.finished = True
            self.capture.finalize()
            raise
        except Exception as exc:
            self.capture.finalize(error=exc, incomplete=True)
            raise

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            close = getattr(self.iterable, "close", None)
            if close:
                close()
        except Exception as exc:
            self.capture.finalize(error=exc, incomplete=True)
            raise
        finally:
            if not self.finished:
                self.capture.finalize(incomplete=True)
