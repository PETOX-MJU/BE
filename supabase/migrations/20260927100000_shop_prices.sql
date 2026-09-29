-- 상점 가격 확정. 시드(20260924090000)는 전부 임시값 12코인이었다.
-- 테마 4개 + 가구 16개를 모두 사려면 680코인이다.
update items set price_coins = 50 where type = 'theme';
update items set price_coins = 30 where type = 'furniture';
