"""
A sharded match counter (inspired by http://code.google.com/appengine/articles/sharding_counters.html)
"""
from google.appengine.ext import db
import random

class MatchesCounter(db.Model):
    """Shards for the counter"""
    count = db.IntegerProperty(required=True, default=0)

NUM_SHARDS = 20

def get_matches_count():
    """Retrieve the value for the sharded matches counter."""
    total = 0
    for counter in MatchesCounter.all():
        total += counter.count
    return total

def increment_matches_count():
    """Increment the value for the sharded matches counter."""
    def txn():
        index = random.randint(0, NUM_SHARDS - 1)
        shard_name = "shard" + str(index)
        counter = MatchesCounter.get_by_key_name(shard_name)
        if counter is None:
            counter = MatchesCounter(key_name=shard_name)
        counter.count += 1
        counter.put()
    db.run_in_transaction(txn)
