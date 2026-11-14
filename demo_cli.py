"""Runs without a browser: python demo_cli.py"""
from forceforge.design import make_truss
from forceforge.physics import solve
from forceforge.robust import Requirements, grid_search, best_feasible
from forceforge.surrogate import train, propose_and_verify
from forceforge.agent import explain_design

if __name__ == "__main__":
    print("=== 2D TRUSS FEA ANALYTIC REFERENCE ===")
    r = solve(make_truss("Triangle", 2, 1, 100, 1000))
    print(f"Apex Uy = {r.disp_m[2,1]*1000:.6f} mm")
    print(f"Member axial forces: {r.force_n.round(4)} N")
    print(f"Support reactions: {r.reactions_n.round(4)} N")
    print("\n=== ROBUST DESIGN SEARCH ===")
    req = Requirements()
    df=grid_search(req)
    print(f"{len(df)} FEA designs evaluated, {int(df.feasible.sum())} feasible")
    print(explain_design(best_feasible(df)))
    print("\n=== MACHINE LEARNING ===")
    ml,cols,metrics=train(df)
    print("Held-out MAE / R2:", metrics)
    verified=propose_and_verify(ml,cols,req,n=300)
    print("ML-proposed, FEA-verified designs:\n",verified.head(3).to_string(index=False))
