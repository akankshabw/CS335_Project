:out = 0
:a = :secret
:b = :pub - :secret
repeat :n [ :a = :a + 1
:b = :b - 1
:out = :out + :a + :b ]