from bioptim import PenaltyController
from casadi import MX, vertcat
from warnings import warn

from .collision import collision_impact


def custom_phase_transition_pre(controllers: list[PenaltyController, PenaltyController]) -> MX:
    """
    The constraint of the transition from an unholonomic to a holonomic model.

    Parameters
    ----------
    controllers: list[PenaltyController, PenaltyController]
        The controller for all the nodes in the penalty

    Returns
    -------
    The constraint such that: q-, qdot- = q+, qdot+
    """

    # Take the values of q of the BioMod without holonomics constraints
    states_pre = vertcat(controllers[0].states["q"].cx, controllers[0].states["qdot"].cx)

    nb_independent = controllers[1].model.nb_independent_joints
    u_post = controllers[1].states.cx[:nb_independent]
    udot_post = controllers[1].states.cx[nb_independent : nb_independent * 2]

    # Take the q of the independent joint and calculate the q of dependent joint
    v_post = controllers[1].model.compute_v_from_u_explicit_symbolic(u_post)
    q_post = controllers[1].model.state_from_partition(u_post, v_post)

    Bvu = controllers[1].model.coupling_matrix(q_post)
    vdot_post = Bvu @ udot_post
    qdot_post = controllers[1].model.state_from_partition(udot_post, vdot_post)

    states_post = vertcat(q_post, qdot_post)

    return states_pre - states_post


def custom_phase_transition_algebraic_post(controllers: list[PenaltyController, PenaltyController]) -> MX:
    """
    The constraint of the transition from a holonomic to an model without holonomic constraints.

    Parameters
    ----------
    controllers: list[PenaltyController, PenaltyController]
        The controller for all the nodes in the penalty

    Returns
    -------
    The constraint such that: (q-, qdot-) = (q+, qdot+)
    """

    u_pre = controllers[0].states["q_u"].cx
    udot_pre = controllers[0].states["qdot_u"].cx
    v_pre = controllers[0].algebraic_states["q_v"].cx

    q_pre = controllers[0].model.state_from_partition(u_pre, v_pre)
    qdot_pre = controllers[0].model.compute_qdot()(q_pre, udot_pre)

    states_pre = vertcat(q_pre[:-1], qdot_pre[:-1])
    states_post = vertcat(controllers[1].states["q"].cx, controllers[1].states["qdot"].cx)

    tau_states_pre = controllers[0].states["tau"].cx
    tau_states_post = controllers[1].states["tau"].cx

    states_pre = vertcat(states_pre, tau_states_pre)
    states_post = vertcat(states_post, tau_states_post)

    return states_pre - states_post


def custom_phase_transition_algebraic_pre(controllers: list[PenaltyController, PenaltyController]) -> MX:
    """
    The constraint of the transition from a holonomic to an model without holonomic constraints.

    Parameters
    ----------
    controllers: list[PenaltyController, PenaltyController]
        The controller for all the nodes in the penalty

    Returns
    -------
    The constraint such that: (q-, qdot-) = (q+, qdot+)
    """
    states_pre = vertcat(controllers[0].states["q"].cx, controllers[0].states["qdot"].cx)

    u_post = controllers[1].states["q_u"].cx
    udot_post = controllers[1].states["qdot_u"].cx
    v_post = controllers[1].algebraic_states["q_v"].cx

    q_post = controllers[1].model.state_from_partition(u_post, v_post)
    qdot_post = controllers[1].model.compute_qdot()(q_post, udot_post)

    states_post = vertcat(q_post[:-1], qdot_post[:-1])

    tau_states_pre = controllers[0].states["tau"].cx
    tau_states_post = controllers[1].states["tau"].cx

    states_pre = vertcat(states_pre, tau_states_pre)
    states_post = vertcat(states_post, tau_states_post)

    return states_pre - states_post


def transition_algebraic_pre_with_collision(controllers: list[PenaltyController, PenaltyController]) -> MX:
    """
    The constraint of the transition from a holonomic to an model without holonomic constraints.

    Parameters
    ----------
    controllers: list[PenaltyController, PenaltyController]
        The controller for all the nodes in the penalty

    Returns
    -------
    The constraint such that: (q-, qdot-) = (q+, qdot+)
    """
    q_pre = controllers[0].states["q"].cx
    qdot_pre = controllers[0].states["qdot"].cx
    # add the position and velocity of the key to zero
    q_pre = vertcat(q_pre, 0)
    qdot_pre = vertcat(qdot_pre, 0)
    qdot_post_estimated = collision_impact(controllers[1].model, q_pre, qdot_pre)

    u_post = controllers[1].states["q_u"].cx
    udot_post = controllers[1].states["qdot_u"].cx
    v_post = controllers[1].algebraic_states["q_v"].cx

    q_post = controllers[1].model.state_from_partition(u_post, v_post)
    qdot_post = controllers[1].model.compute_qdot()(q_post, udot_post)

    tau_states_pre = controllers[0].states["tau"].cx
    tau_states_post = controllers[1].states["tau"].cx

    return vertcat(q_pre - q_post, qdot_post_estimated - qdot_post, tau_states_pre - tau_states_post)


def custom_takeoff(controllers: list[PenaltyController, PenaltyController]):
    """
    A discontinuous function that simulates an inelastic impact of a new contact point

    Parameters
    ----------
    transition: PhaseTransition
        A reference to the phase transition
    controllers: list[PenaltyController, PenaltyController]
            The penalty node elements

    Returns
    -------
    The difference between the last and first node after applying the impulse equations
    """

    ocp = controllers[0].ocp

    # Aliases
    pre, post = controllers
    if pre.model.nb_rigid_contacts == 0:
        warn("The chosen model does not have any rigid contact")

    q_pre = pre.states["q"].mx
    qdot_pre = pre.states["qdot"].mx

    val = []
    cx_start = []
    cx_end = []
    for key in pre.states:
        cx_end = vertcat(cx_end, pre.states[key].mapping.to_second.map(pre.states[key].cx))
        cx_start = vertcat(cx_start, post.states[key].mapping.to_second.map(post.states[key].cx))
        post_mx = post.states[key].mx
        if key == "tau":
            continuity = 0  # skip tau continuity
        else:
            continuity = post.states[key].mapping.to_first.map(pre.states[key].mx - post_mx)

        val = vertcat(val, continuity)

    name = f"PHASE_TRANSITION_{pre.phase_idx % ocp.n_phases}_{post.phase_idx % ocp.n_phases}"
    func = pre.to_casadi_func(name, val, pre.states.mx, post.states.mx)(cx_end, cx_start)
    return func


def continuity_only_q_and_qdot(controllers: list[PenaltyController, PenaltyController]):
    """
    A discontinuous function that simulates an inelastic impact of a new contact point

    Parameters
    ----------
    transition: PhaseTransition
        A reference to the phase transition
    controllers: list[PenaltyController, PenaltyController]
            The penalty node elements

    Returns
    -------
    The difference between the last and first node after applying the impulse equations
    """

    ocp = controllers[0].ocp

    # Aliases
    pre, post = controllers

    q_pre = pre.states["q"].mx
    qdot_pre = pre.states["qdot"].mx

    val = []
    cx_start = []
    cx_end = []
    for key in pre.states:
        cx_end = vertcat(cx_end, pre.states[key].mapping.to_second.map(pre.states[key].cx))
        cx_start = vertcat(cx_start, post.states[key].mapping.to_second.map(post.states[key].cx))
        post_mx = post.states[key].mx
        if key == "tau":
            continuity = 0  # skip tau continuity
        else:
            continuity = post.states[key].mapping.to_first.map(pre.states[key].mx - post_mx)

        val = vertcat(val, continuity)

    name = f"PHASE_TRANSITION_{pre.phase_idx % ocp.n_phases}_{post.phase_idx % ocp.n_phases}"
    func = pre.to_casadi_func(name, val, pre.states.mx, post.states.mx)(cx_end, cx_start)
    return func
