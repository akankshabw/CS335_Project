:out = 0
:temp = :secret
repeat :n [ :temp = :temp + :pub
:out = :out + :temp
:temp = :temp - :pub
:out = :out - :temp ]