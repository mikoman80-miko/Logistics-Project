import pickle
import zlib

from django.core.cache.backends.filebased import FileBasedCache


class SafeFileBasedCache(FileBasedCache):
    """깨진 캐시 파일(쓰는 도중 서버가 꺼진 경우 등)을 값이 없는 것으로 보고 지웁니다.

    기본 파일 캐시는 깨진 파일을 읽으면 오류를 내서, 그 접속 주소·계정의 로그인이 500 오류로 계속 막혔습니다.
    """

    def get(self, key, default=None, version=None):
        try:
            return super().get(key, default, version)
        except (pickle.UnpicklingError, zlib.error, EOFError, ValueError):
            self.delete(key, version)
            return default
