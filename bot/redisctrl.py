import socket
import redis

hostname = "localhost"
port = 6379
address = f"redis://{hostname}:{port}"

bot_db = 15

def is_redis_up() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((hostname, port)) == 0

def get_bot_db():
    rdb = redis.Redis(
        host=hostname,
        port=port,
        db = bot_db)
    return(rdb)
