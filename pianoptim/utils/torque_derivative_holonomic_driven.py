from typing import Callable

from bioptim import (
    DynamicsFcn,
    DynamicsFunctions,
    DynamicsEvaluation,
    ConfigureProblem,
    BiMapping,
    CustomPlot,
    PlotType,
    PenaltyController,
)
from casadi import MX, vertcat, Function
import numpy as np


def configure_holonomic_torque_derivative_driven(
    ocp, nlp, numerical_data_timeseries: dict[str, np.ndarray] = None, custom_q_v_init: np.ndarray = None
):
    """
    Tell the program which variables are states and controls.

    Parameters
    ----------
    ocp: OptimalControlProgram
        A reference to the ocp
    nlp: NonLinearProgram
        A reference to the phase
    """

    name = "q_u"
    names_u = [nlp.model.name_dof[i] for i in nlp.model.independent_joint_index]
    ConfigureProblem.configure_new_variable(
        name,
        names_u,
        ocp,
        nlp,
        True,
        False,
        False,
        # NOTE: not ready for phase mapping yet as it is based on dofnames of the class BioModel
        # see _set_kinematic_phase_mapping method
        # axes_idx=ConfigureProblem._apply_phase_mapping(ocp, nlp, name),
    )

    name = "qdot_u"
    names_qdot = ConfigureProblem._get_kinematics_based_names(nlp, "qdot")
    names_udot = [names_qdot[i] for i in nlp.model.independent_joint_index]
    ConfigureProblem.configure_new_variable(
        name,
        names_udot,
        ocp,
        nlp,
        True,
        False,
        False,
        # NOTE: not ready for phase mapping yet as it is based on dofnames of the class BioModel
        # see _set_kinematic_phase_mapping method
        # axes_idx=ConfigureProblem._apply_phase_mapping(ocp, nlp, name),
    )

    ConfigureProblem.configure_tau(ocp, nlp, as_states=True, as_controls=False)
    ConfigureProblem.configure_taudot(ocp, nlp, as_states=False, as_controls=True)

    # extra plots
    ConfigureProblem.configure_qv(ocp, nlp, nlp.model.compute_q_v)
    ConfigureProblem.configure_qdotv(ocp, nlp, nlp.model._compute_qdot_v)
    configure_lagrange_multipliers_function(
        ocp, nlp, nlp.model.compute_the_lagrangian_multipliers, custom_q_v_init=custom_q_v_init
    )

    ConfigureProblem.configure_dynamics_function(
        ocp, nlp, holonomic_torque_derivative_driven_custom_qv_init, custom_q_v_init=custom_q_v_init
    )


def configure_holonomic_torque_derivative_driven_with_qv(
    ocp, nlp, numerical_data_timeseries: dict[str, np.ndarray] = None, custom_q_v_init: np.ndarray = None
):
    """
    Tell the program which variables are states and controls.

    Parameters
    ----------
    ocp: OptimalControlProgram
        A reference to the ocp
    nlp: NonLinearProgram
        A reference to the phase
    """

    name = "q_u"
    names_u = [nlp.model.name_dof[i] for i in nlp.model.independent_joint_index]
    ConfigureProblem.configure_new_variable(
        name,
        names_u,
        ocp,
        nlp,
        True,
        False,
        False,
        # NOTE: not ready for phase mapping yet as it is based on dofnames of the class BioModel
        # see _set_kinematic_phase_mapping method
        # axes_idx=ConfigureProblem._apply_phase_mapping(ocp, nlp, name),
    )
    name = "q_v"
    names_v = [nlp.model.name_dof[i] for i in nlp.model.dependent_joint_index]
    ConfigureProblem.configure_new_variable(
        name,
        names_v,
        ocp,
        nlp,
        False,
        False,
        False,
        as_algebraic_states=True,
    )

    name = "qdot_u"
    names_qdot = ConfigureProblem._get_kinematics_based_names(nlp, "qdot")
    names_udot = [names_qdot[i] for i in nlp.model.independent_joint_index]
    ConfigureProblem.configure_new_variable(
        name,
        names_udot,
        ocp,
        nlp,
        True,
        False,
        False,
        # NOTE: not ready for phase mapping yet as it is based on dofnames of the class BioModel
        # see _set_kinematic_phase_mapping method
        # axes_idx=ConfigureProblem._apply_phase_mapping(ocp, nlp, name),
    )

    ConfigureProblem.configure_tau(ocp, nlp, as_states=True, as_controls=False)
    ConfigureProblem.configure_taudot(ocp, nlp, as_states=False, as_controls=True)

    # extra plots
    ConfigureProblem.configure_qdotv(ocp, nlp, nlp.model._compute_qdot_v)
    configure_lagrange_multipliers_function(
        ocp, nlp, nlp.model.compute_the_lagrangian_multipliers, custom_q_v_init=custom_q_v_init
    )

    ConfigureProblem.configure_dynamics_function(ocp, nlp, holonomic_torque_derivative_driven_with_qv)


def configure_lagrange_multipliers_function(ocp, nlp, dyn_func: Callable, custom_q_v_init):
    """
    Configure the contact points

    Parameters
    ----------
    ocp: OptimalControlProgram
        A reference to the ocp
    nlp: NonLinearProgram
        A reference to the phase
    dyn_func: Callable[time, states, controls, param, algebraic_states, numerical_timeseries]
        The function to get the values of contact forces from the dynamics
    """

    time_span_sym = vertcat(nlp.time_cx, nlp.dt)
    nlp.lagrange_multipliers_function = Function(
        "lagrange_multipliers_function",
        [
            time_span_sym,
            nlp.states.scaled.cx,
            nlp.controls.scaled.cx,
            nlp.parameters.scaled.cx,
            nlp.algebraic_states.scaled.cx,
            nlp.numerical_timeseries.cx,
        ],
        [
            dyn_func()(
                nlp.get_var_from_states_or_controls("q_u", nlp.states.scaled.cx, nlp.controls.scaled.cx),
                nlp.get_var_from_states_or_controls("qdot_u", nlp.states.scaled.cx, nlp.controls.scaled.cx),
                custom_q_v_init,
                nlp.get_var_from_states_or_controls("tau", nlp.states.scaled.cx, nlp.controls.scaled.cx),
            )
        ],
        ["t_span", "x", "u", "p", "a", "d"],
        ["lagrange_multipliers"],
    )

    all_multipliers_names = []
    for nlp_i in ocp.nlp:
        if hasattr(nlp_i.model, "has_holonomic_constraints"):  # making sure we have a HolonomicBiorbdModel
            nlp_i_multipliers_names = [nlp_i.model.name_dof[i] for i in nlp_i.model.dependent_joint_index]
            all_multipliers_names.extend(
                [name for name in nlp_i_multipliers_names if name not in all_multipliers_names]
            )

    all_multipliers_names = [f"lagrange_multiplier_{name}" for name in all_multipliers_names]
    all_multipliers_names_in_phase = [
        f"lagrange_multiplier_{nlp.model.name_dof[i]}" for i in nlp.model.dependent_joint_index
    ]

    axes_idx = BiMapping(
        to_first=[i for i, c in enumerate(all_multipliers_names) if c in all_multipliers_names_in_phase],
        to_second=[i for i, c in enumerate(all_multipliers_names) if c in all_multipliers_names_in_phase],
    )

    nlp.plot["lagrange_multipliers"] = CustomPlot(
        lambda t0, phases_dt, node_idx, x, u, p, a, d: nlp.lagrange_multipliers_function(
            np.concatenate([t0, t0 + phases_dt[nlp.phase_idx]]), x, u, p, a, d
        ),
        plot_type=PlotType.INTEGRATED,
        axes_idx=axes_idx,
        legend=all_multipliers_names,
    )


def holonomic_torque_derivative_driven_custom_qv_init(
    time: MX.sym,
    states: MX.sym,
    controls: MX.sym,
    parameters: MX.sym,
    algebraic_states: MX.sym,
    numerical_timeseries: MX.sym,
    nlp,
    external_forces: list = None,
    custom_q_v_init: np.ndarray = None,
) -> DynamicsEvaluation:
    """
    The custom dynamics function that provides the derivative of the states: dxdt = f(t, x, u, p, a, d)

    Parameters
    ----------
    time: MX.sym
        The time of the system
    states: MX.sym
        The state of the system
    controls: MX.sym
        The controls of the system
    parameters: MX.sym
        The parameters acting on the system
    algebraic_states: MX.sym
        The algebraic states of the system
    numerical_timeseries: MX.sym
        The numerical timeseries of the system
    nlp: NonLinearProgram
        A reference to the phase
    external_forces: list[Any]
        The external forces
    custom_q_v_init: np.ndarray
        The custom qv_init

    Returns
    -------
    The derivative of the states in the tuple[MX | SX] format
    """

    q_u = DynamicsFunctions.get(nlp.states["q_u"], states)
    qdot_u = DynamicsFunctions.get(nlp.states["qdot_u"], states)
    tau = DynamicsFunctions.get(nlp.states["tau"], states)
    taudot = controls
    qddot_u = nlp.model.partitioned_forward_dynamics()(q_u, qdot_u, custom_q_v_init, tau)

    return DynamicsEvaluation(dxdt=vertcat(qdot_u, qddot_u, taudot), defects=None)


def holonomic_torque_derivative_driven_with_qv(
    time,
    states,
    controls,
    parameters,
    algebraic_states,
    numerical_timeseries,
    nlp,
) -> DynamicsEvaluation:
    """
    The custom dynamics function that provides the derivative of the states: dxdt = f(t, x, u, p, a, d)

    Parameters
    ----------
    time: MX.sym | SX.sym
        The time of the system
    states: MX.sym | SX.sym
        The state of the system
    controls: MX.sym | SX.sym
        The controls of the system
    parameters: MX.sym | SX.sym
        The parameters acting on the system
    algebraic_states: MX.sym | SX.sym
        The algebraic states of the system
    numerical_timeseries: MX.sym | SX.sym
        The numerical timeseries of the system
    nlp: NonLinearProgram
        A reference to the phase

    Returns
    -------
    The derivative of the states in the tuple[MX | SX] format
    """

    q_v = DynamicsFunctions.get(nlp.algebraic_states["q_v"], algebraic_states)
    q_u = DynamicsFunctions.get(nlp.states["q_u"], states)
    qdot_u = DynamicsFunctions.get(nlp.states["qdot_u"], states)
    tau = DynamicsFunctions.get(nlp.states["tau"], states)
    taudot = controls
    qddot_u = nlp.model.partitioned_forward_dynamics_with_qv()(q_u, q_v, qdot_u, tau)

    return DynamicsEvaluation(dxdt=vertcat(qdot_u, qddot_u, taudot), defects=None)


def holonomic_torque_derivative_driven_with_qv_spring(
    time,
    states,
    controls,
    parameters,
    algebraic_states,
    numerical_timeseries,
    nlp,
) -> DynamicsEvaluation:
    """
    The custom dynamics function that provides the derivative of the states: dxdt = f(t, x, u, p, a, d)

    Parameters
    ----------
    time: MX.sym | SX.sym
        The time of the system
    states: MX.sym | SX.sym
        The state of the system
    controls: MX.sym | SX.sym
        The controls of the system
    parameters: MX.sym | SX.sym
        The parameters acting on the system
    algebraic_states: MX.sym | SX.sym
        The algebraic states of the system
    numerical_timeseries: MX.sym | SX.sym
        The numerical timeseries of the system
    nlp: NonLinearProgram
        A reference to the phase

    Returns
    -------
    The derivative of the states in the tuple[MX | SX] format
    """

    q_v = DynamicsFunctions.get(nlp.algebraic_states["q_v"], algebraic_states)
    q_u = DynamicsFunctions.get(nlp.states["q_u"], states)
    qdot_u = DynamicsFunctions.get(nlp.states["qdot_u"], states)
    tau = DynamicsFunctions.get(nlp.states["tau"], states)

    q = nlp.model.state_from_partition(q_u, q_v)

    tau_spring = nlp.model.compute_spring_force(q)
    tau[-1] += tau_spring

    taudot = controls
    qddot_u = nlp.model.partitioned_forward_dynamics_with_qv()(q_u, q_v, qdot_u, tau)

    return DynamicsEvaluation(dxdt=vertcat(qdot_u, qddot_u, taudot), defects=None)


def constraint_holonomic_end(
    controllers: PenaltyController,
):
    """
    Minimize the distance between two markers
    By default this function is quadratic, meaning that it minimizes distance between them.

    Parameters
    ----------
    controller: PenaltyController
        The penalty node elements
    """

    q_u = controllers.states["q_u"]
    q_u_complete = q_u.mapping.to_second.map(q_u.cx)

    q_v = controllers.algebraic_states["q_v"]
    q_v_complete = q_v.mapping.to_second.map(q_v.cx)

    q = controllers.model.state_from_partition(q_u_complete, q_v_complete)

    return controllers.model.holonomic_constraints(q)


def constraint_holonomic(
    controllers: PenaltyController,
):
    """
    Minimize the distance between two markers
    By default this function is quadratic, meaning that it minimizes distance between them.

    Parameters
    ----------
    controller: PenaltyController
        The penalty node elements
    """

    q_u = controllers.states["q_u"]
    q_u_complete = q_u.mapping.to_second.map(q_u.cx)

    q_v = controllers.algebraic_states["q_v"]
    q_v_complete = q_v.mapping.to_second.map(q_v.cx)

    q = controllers.model.state_from_partition(q_u_complete, q_v_complete)

    holonomic_constraints = controllers.model.holonomic_constraints(q)

    for q_u_cx, q_v_cx in zip(q_u.cx_intermediates_list, q_v.cx_intermediates_list):
        q_u_complete = q_u.mapping.to_second.map(q_u_cx)
        q_v_complete = q_v.mapping.to_second.map(q_v_cx)
        q = controllers.model.state_from_partition(q_u_complete, q_v_complete)
        holonomic_constraints = vertcat(holonomic_constraints, controllers.model.holonomic_constraints(q))

    return holonomic_constraints
