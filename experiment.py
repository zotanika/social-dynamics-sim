import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class SimulationConfig:
    """Configuration parameters for the social dynamics simulation."""
    # Simulation settings
    N: int = 10000  # Population size (number of agents)
    T: int = 100  # Simulation duration (time steps)
    seed: int = 0  # Random seed for reproducibility
    maginot_threshold: float = 0.2  # Critical resilience threshold (R_crit) for defining collapse (Maginot Time)

    # Empathy distribution parameters
    # Empathy E_i is drawn from a mixture of Gaussians
    mu_A: float = 1.3  # Mean empathy for the "high empathy" sub-population
    mu_B: float = 1.0  # Mean empathy for the "low empathy" sub-population
    sigma_E: float = 0.1  # Standard deviation for empathy distribution

    # Stress model parameters
    # Perceived stress S_i = E_i^alpha * (1 + beta * G)
    alpha: float = 1.3  # Nonlinearity of empathy's effect on stress (alpha > 1 amplifies effect for high empathy)
    beta: float = 0.4  # Network gain parameter (strength of amplification via connectivity G)

    # Initial state
    initial_resilience_mean: float = 0.5  # Mean of initial resilience distribution
    initial_resilience_std: float = 0.08  # Standard deviation of initial resilience
    initial_grouping: float = 0.3  # Initial grouping level (G_0)

    # Dynamics parameters - Society A (Adaptive / Agency-oriented)
    # R_A(t+1) = R_A + k_A * R_A * (1 - R_A) - lambda_A * S_A
    # G_A(t+1) = max(0, G_A * (1 - eta_A))
    k_A: float = 0.09  # Intrinsic resilience growth rate (adaptation rate)
    lambda_A: float = 0.005  # Resilience erosion coefficient due to stress
    eta_A: float = 0.05  # De-grouping rate (tendency to reduce group cohesion)

    # Dynamics parameters - Society B (Overprotective / Support-centric)
    # R_B(t+1) = R_B - k_B * S_B + d_B
    # G_B(t+1) = max(0, G_B + gamma_B * mean(S_B) - eta_B * G_B)
    k_B: float = 0.03  # Resilience erosion coefficient due to stress
    d_B: float = 0.02  # Baseline external support (safety net / buffering)
    eta_B: float = 0.03  # De-grouping / forgetting rate
    k_B: float = 0.03  # Resilience erosion coefficient due to stress
    d_B: float = 0.02  # Baseline external support (safety net / buffering)
    eta_B: float = 0.03  # De-grouping / forgetting rate
    gamma_B: float = 0.005  # Reactivity of grouping to stress (stress-driven grouping)

    # Network / Local Coupling parameters
    use_local_grouping: bool = False # If True, G is a vector varying by agent based on neighbors
    n_neighbors: int = 20  # Number of neighbors for local coupling (Small World / Random)
    rewiring_prob: float = 0.1 # Probability of rewiring (for Watts-Strogatz small world)

def common_plot_style():
    plt.style.use('default')  # Reset to default first
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'axes.grid': True,
        'grid.alpha': 0.3,
        'lines.linewidth': 2,
        'axes.titlesize': 14,
        'axes.labelsize': 12,
        'legend.fontsize': 10,
        'figure.figsize': (10, 6),
        'figure.dpi': 100,
    })

class SocialDynamicsSimulation:
    def __init__(self, config: SimulationConfig = SimulationConfig()):
        self.config = config
        self.rng = np.random.default_rng(config.seed)
        self.history: Dict[str, List[float]] = {
            k: [] for k in ['R_A', 'R_B', 'G_A', 'G_B']
        }
        self.t_collapse: Optional[int] = None
        
        self._initialize_population()
        if self.config.use_local_grouping:
             self._initialize_network()
        self._initialize_state()

    def _initialize_network(self):
        """Create a Small-World network adjacency list for local interactions."""
        # Simple Watts-Strogatz implementation using numpy
        N = self.config.N
        k = self.config.n_neighbors
        p = self.config.rewiring_prob
        
        # 1. Regular ring lattice
        self.neighbors = np.zeros((N, k), dtype=int)
        for i in range(N):
            for j in range(1, k // 2 + 1):
                self.neighbors[i, j-1] = (i + j) % N
                self.neighbors[i, k // 2 + j - 1] = (i - j) % N
        
        # 2. Random rewiring (simplified: just randomizing a fraction of indices)
        # For a truly rigorous WS we'd iterate edges, but for this mean-field-plus 
        # extension, purely randomizing a fraction of neighbor pointers is sufficient 
        # to break local clusters matches the 'Small World' intent.
        mask = self.rng.random(self.neighbors.shape) < p
        random_neighbors = self.rng.integers(0, N, size=self.neighbors.shape)
        self.neighbors = np.where(mask, random_neighbors, self.neighbors)

    def _initialize_population(self):
        N = self.config.N
        is_high_empathy_group = self.rng.random(N) < 0.5
        mu = self.config.mu_B + is_high_empathy_group * \
             (self.config.mu_A - self.config.mu_B)
        self.E = self.rng.normal(mu, self.config.sigma_E, size=N)
        self.E = np.clip(self.E, 0.0, None)

    def _initialize_state(self):
        N = self.config.N
        R_init = self.rng.normal(
            self.config.initial_resilience_mean, 
            self.config.initial_resilience_std, 
            size=N
        )
        R_init = np.clip(R_init, 0.0, 1.0)
        self.R_A = R_init.copy()
        self.R_B = R_init.copy()
        
        if self.config.use_local_grouping:
            # G becomes a vector of size N
            self.G_A = np.full(N, self.config.initial_grouping)
            self.G_B = np.full(N, self.config.initial_grouping)
        else:
            # G is a scalar
            self.G_A = self.config.initial_grouping
            self.G_B = self.config.initial_grouping

    def calculate_stress(self, G: float | np.ndarray) -> np.ndarray:
        return (self.E ** self.config.alpha) * (1 + self.config.beta * G)

    def step(self, t: int):
        S_A = self.calculate_stress(self.G_A)
        S_B = self.calculate_stress(self.G_B)

        # Update Resilience
        self.R_A = (self.R_A
                    + self.config.k_A * self.R_A * (1 - self.R_A)
                    - self.config.lambda_A * S_A)
        self.R_B = (self.R_B
                    - self.config.k_B * S_B
                    + self.config.d_B)
        
        self.R_A = np.clip(self.R_A, 0.0, 1.0)
        self.R_B = np.clip(self.R_B, 0.0, 1.0)

        # Social Cost & Update Grouping
        # If scalar, C_B is scalar mean. If vector, C_B depends on neighbors.
        
        if self.config.use_local_grouping:
            # Calculate local average stress for each agent
            # S_B is (N,), neighbors is (N, k)
            # We want C_B[i] = mean(S_B[neighbors[i]])
            neighbor_stress = S_B[self.neighbors] # Shape (N, k)
            C_B_local = neighbor_stress.mean(axis=1) # Shape (N,)
            
            self.G_A = np.maximum(0.0, self.G_A * (1 - self.config.eta_A))
            self.G_B = np.maximum(
                0.0, 
                self.G_B + self.config.gamma_B * C_B_local - self.config.eta_B * self.G_B
            )
            
            # For history, store the mean G
            self.history['G_A'].append(self.G_A.mean())
            self.history['G_B'].append(self.G_B.mean())
            
        else:
            C_B = S_B.mean()
            self.G_A = max(0.0, self.G_A * (1 - self.config.eta_A))
            self.G_B = max(
                0.0, 
                self.G_B + self.config.gamma_B * C_B - self.config.eta_B * self.G_B
            )

            self.history['G_A'].append(self.G_A)
            self.history['G_B'].append(self.G_B)
        
        self.history['R_A'].append(self.R_A.mean())
        self.history['R_B'].append(self.R_B.mean())

        if (self.t_collapse is None 
                and self.history['R_B'][-1] < self.config.maginot_threshold):
            self.t_collapse = t

    def run(self):
        for t in range(self.config.T):
            self.step(t)
        return self.history

    def plot_results(self):
        common_plot_style()
        t_axis = range(len(self.history['R_A']))
        plt.figure()
        plt.plot(t_axis, self.history['R_A'], label='Society A (Adaptive)')
        plt.plot(t_axis, self.history['R_B'], label='Society B (Support-centric)')
        plt.axhline(self.config.maginot_threshold,
                    color='r', linestyle='--',
                    label='Maginot Threshold')
        if self.t_collapse is not None:
            plt.axvline(self.t_collapse,
                        color='k', linestyle=':',
                        label=f'Collapse at t={self.t_collapse}')
        plt.title('Average Resilience Over Time')
        plt.xlabel('Time Step')
        plt.ylabel('Average Resilience')
        plt.legend()
        plt.tight_layout()
        plt.savefig('fig_resilience.pdf')

def run_sensitivity_analysis():
    common_plot_style()
    alpha_values = np.linspace(1.0, 1.8, 20)
    final_resilience_B = []
    collapse_times = []

    for alpha in alpha_values:
        cfg = SimulationConfig(alpha=alpha, T=100, seed=42)
        sim = SocialDynamicsSimulation(cfg)
        sim.run()
        
        final_resilience_B.append(sim.history['R_B'][-1])
        if sim.t_collapse is not None:
            collapse_times.append(sim.t_collapse)
        else:
            collapse_times.append(cfg.T)

    fig, ax1 = plt.subplots()

    color = 'tab:blue'
    ax1.set_xlabel(r'Empathy Nonlinearity ($\alpha$)')
    ax1.set_ylabel('Final Resilience (Society B)', color=color)
    ax1.plot(alpha_values, final_resilience_B,
             color=color, marker='o', label='Final Resilience')
    ax1.tick_params(axis='y', labelcolor=color)

    ax2 = ax1.twinx()
    color = 'tab:red'
    ax2.set_ylabel('Time to Collapse ($t_{mag}$)', color=color)
    ax2.plot(alpha_values, collapse_times,
             color=color, linestyle='--', marker='x',
             label='Collapse Time')
    ax2.tick_params(axis='y', labelcolor=color)

    plt.title(r'Sensitivity Analysis: Impact of $\alpha$ '
              r'on Society B Stability')
    fig.tight_layout()
    plt.savefig('fig_sensitivity.pdf')

if __name__ == "__main__":
    sim = SocialDynamicsSimulation()
    sim.run()
    print(f"Simulation complete. Collapse time for Society B: {sim.t_collapse}")
    sim.plot_results()
    
    run_sensitivity_analysis()
