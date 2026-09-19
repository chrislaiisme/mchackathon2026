"""Creative shopper-facing services built on top of the ranking engine.

  travel_capsule  旅行打包膠囊衣櫥：少少幾件，換出最多套穿搭
  dress_code      服裝規定解碼器：把邀請函上的 dress code 翻成可檢索的條件
  rent_or_buy     租還是買：一年穿一次的驚艷單品，租比較划算
"""

from .dress_code import decode
from .rent_or_buy import advise
from .travel_capsule import plan_capsule

__all__ = ["plan_capsule", "decode", "advise"]
