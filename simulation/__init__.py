"""
Emergence — Environment Simulation Layer

Provides probability-driven dynamic environment behavior for realistic
IoT vulnerability testing. Manipulates Docker containers between training
loop iterations to simulate service outages, firmware patches, credential
rotations, and detection noise.

All events are probability rolls controlled by a seed for full reproducibility.
"""
