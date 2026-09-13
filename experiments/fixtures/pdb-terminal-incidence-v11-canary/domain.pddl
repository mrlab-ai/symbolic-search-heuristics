(define (domain terminal-incidence-v11-canary)
  (:requirements :strips :action-costs)
  (:predicates (at-a) (at-b) (at-c))
  (:functions (total-cost))

  (:action move-a-b
    :parameters ()
    :precondition (at-a)
    :effect (and
      (not (at-a))
      (at-b)
      (increase (total-cost) 1)))

  (:action move-b-c
    :parameters ()
    :precondition (at-b)
    :effect (and
      (not (at-b))
      (at-c)
      (increase (total-cost) 2))))
