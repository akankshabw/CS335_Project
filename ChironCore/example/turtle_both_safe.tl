:masked = :pub + :secret
:unmasked = :masked - :secret
forward :unmasked
backward :unmasked
