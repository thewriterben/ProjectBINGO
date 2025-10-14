"""
AI-Powered Manufacturing Optimizer

This module provides AI-driven optimization for manufacturing processes,
including cost estimation, production time prediction, and manufacturer matching.
"""

import json
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class ManufacturingRequest:
    """Data class for manufacturing request"""
    product_name: str
    specifications: str
    quantity: int
    material: str
    dimensions: Dict[str, float]
    tolerance: float
    deadline: str


@dataclass
class ManufacturerProfile:
    """Data class for manufacturer profile"""
    id: str
    name: str
    capabilities: List[str]
    materials: List[str]
    capacity: int
    rating: float
    location: str
    hourly_rate: float


class ManufacturingOptimizer:
    """AI-powered optimizer for manufacturing operations"""
    
    def __init__(self):
        self.model_version = "1.0.0"
        self.optimization_weights = {
            "cost": 0.35,
            "quality": 0.30,
            "time": 0.20,
            "sustainability": 0.15
        }
    
    def estimate_cost(self, request: ManufacturingRequest) -> Dict[str, Any]:
        """
        Estimate manufacturing cost using AI model
        
        Args:
            request: Manufacturing request details
            
        Returns:
            Dictionary with cost breakdown
        """
        # Base cost calculation (simplified AI simulation)
        material_cost = self._calculate_material_cost(request)
        labor_cost = self._calculate_labor_cost(request)
        overhead = (material_cost + labor_cost) * 0.15
        
        total_cost = material_cost + labor_cost + overhead
        
        return {
            "total_cost": round(total_cost, 2),
            "material_cost": round(material_cost, 2),
            "labor_cost": round(labor_cost, 2),
            "overhead": round(overhead, 2),
            "cost_per_unit": round(total_cost / request.quantity, 2),
            "confidence": 0.85
        }
    
    def predict_production_time(self, request: ManufacturingRequest) -> Dict[str, Any]:
        """
        Predict production time using AI model
        
        Args:
            request: Manufacturing request details
            
        Returns:
            Dictionary with time estimates
        """
        # AI-based time prediction (simplified)
        base_time = request.quantity * 2.5  # hours per unit
        setup_time = 8  # hours
        quality_control = request.quantity * 0.5
        
        total_time = base_time + setup_time + quality_control
        
        return {
            "total_hours": round(total_time, 2),
            "production_days": round(total_time / 8, 1),
            "setup_time": setup_time,
            "production_time": round(base_time, 2),
            "qc_time": round(quality_control, 2),
            "confidence": 0.80
        }
    
    def match_manufacturers(
        self, 
        request: ManufacturingRequest,
        manufacturers: List[ManufacturerProfile]
    ) -> List[Dict[str, Any]]:
        """
        Match and rank manufacturers using AI algorithm
        
        Args:
            request: Manufacturing request details
            manufacturers: List of available manufacturers
            
        Returns:
            Ranked list of manufacturers with match scores
        """
        matches = []
        
        for manufacturer in manufacturers:
            score = self._calculate_match_score(request, manufacturer)
            
            if score > 0.5:  # Threshold for viable match
                matches.append({
                    "manufacturer_id": manufacturer.id,
                    "manufacturer_name": manufacturer.name,
                    "match_score": round(score, 3),
                    "estimated_cost": self._estimate_manufacturer_cost(request, manufacturer),
                    "estimated_days": self._estimate_delivery_time(request, manufacturer),
                    "rating": manufacturer.rating,
                    "recommendation": self._get_recommendation(score)
                })
        
        # Sort by match score
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        
        return matches
    
    def optimize_production_schedule(
        self,
        orders: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Optimize production schedule for multiple orders
        
        Args:
            orders: List of manufacturing orders
            
        Returns:
            Optimized schedule
        """
        # AI-driven scheduling optimization
        schedule = []
        
        # Sort orders by priority (deadline and value)
        sorted_orders = sorted(
            orders,
            key=lambda x: (x.get("priority", 1), -x.get("value", 0))
        )
        
        current_time = 0
        for order in sorted_orders:
            estimated_hours = order.get("estimated_hours", 24)
            schedule.append({
                "order_id": order["order_id"],
                "start_time": current_time,
                "end_time": current_time + estimated_hours,
                "duration": estimated_hours
            })
            current_time += estimated_hours
        
        return {
            "schedule": schedule,
            "total_time": current_time,
            "efficiency_score": 0.87,
            "optimization_applied": True
        }
    
    def analyze_quality_requirements(self, specifications: str) -> Dict[str, Any]:
        """
        Analyze quality requirements from specifications
        
        Args:
            specifications: Product specifications text
            
        Returns:
            Quality analysis results
        """
        # AI-based specification analysis
        quality_level = "high" if "precision" in specifications.lower() else "standard"
        
        return {
            "quality_level": quality_level,
            "critical_dimensions": [],
            "tolerances": "standard",
            "inspection_points": 3,
            "certifications_required": [],
            "complexity_score": 0.65
        }
    
    # Private helper methods
    
    def _calculate_material_cost(self, request: ManufacturingRequest) -> float:
        """Calculate material cost"""
        material_rates = {
            "steel": 5.0,
            "aluminum": 8.0,
            "plastic": 3.0,
            "wood": 2.5,
            "composite": 12.0
        }
        rate = material_rates.get(request.material.lower(), 5.0)
        volume = self._calculate_volume(request.dimensions)
        return rate * volume * request.quantity
    
    def _calculate_labor_cost(self, request: ManufacturingRequest) -> float:
        """Calculate labor cost"""
        base_rate = 50.0  # per hour
        hours_per_unit = 2.5
        return base_rate * hours_per_unit * request.quantity
    
    def _calculate_volume(self, dimensions: Dict[str, float]) -> float:
        """Calculate volume from dimensions"""
        return dimensions.get("length", 1) * dimensions.get("width", 1) * dimensions.get("height", 1)
    
    def _calculate_match_score(
        self,
        request: ManufacturingRequest,
        manufacturer: ManufacturerProfile
    ) -> float:
        """Calculate manufacturer match score"""
        score = 0.0
        
        # Capability match
        if request.material in manufacturer.materials:
            score += 0.3
        
        # Capacity match
        if manufacturer.capacity >= request.quantity:
            score += 0.25
        
        # Rating weight
        score += (manufacturer.rating / 5.0) * 0.25
        
        # Location and other factors
        score += 0.2
        
        return min(score, 1.0)
    
    def _estimate_manufacturer_cost(
        self,
        request: ManufacturingRequest,
        manufacturer: ManufacturerProfile
    ) -> float:
        """Estimate cost for specific manufacturer"""
        base_cost = self.estimate_cost(request)["total_cost"]
        # Adjust based on manufacturer's rate
        rate_factor = manufacturer.hourly_rate / 50.0
        return round(base_cost * rate_factor, 2)
    
    def _estimate_delivery_time(
        self,
        request: ManufacturingRequest,
        manufacturer: ManufacturerProfile
    ) -> int:
        """Estimate delivery time for specific manufacturer"""
        base_time = self.predict_production_time(request)["production_days"]
        # Adjust based on manufacturer capacity
        capacity_factor = 1.0 if manufacturer.capacity >= request.quantity else 1.5
        return int(base_time * capacity_factor)
    
    def _get_recommendation(self, score: float) -> str:
        """Get recommendation based on match score"""
        if score >= 0.9:
            return "Excellent match - Highly recommended"
        elif score >= 0.75:
            return "Good match - Recommended"
        elif score >= 0.6:
            return "Fair match - Consider for backup"
        else:
            return "Low match - Not recommended"


# API Interface for the AI module
class AIServiceAPI:
    """REST API interface for AI service"""
    
    def __init__(self):
        self.optimizer = ManufacturingOptimizer()
    
    def process_request(self, request_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process AI service request
        
        Args:
            request_type: Type of request (estimate, predict, match, optimize)
            data: Request data
            
        Returns:
            Processing result
        """
        handlers = {
            "estimate_cost": self._handle_cost_estimation,
            "predict_time": self._handle_time_prediction,
            "match_manufacturers": self._handle_manufacturer_matching,
            "optimize_schedule": self._handle_schedule_optimization,
            "analyze_quality": self._handle_quality_analysis
        }
        
        handler = handlers.get(request_type)
        if handler:
            return handler(data)
        else:
            return {"error": "Unknown request type"}
    
    def _handle_cost_estimation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle cost estimation request"""
        request = ManufacturingRequest(**data)
        return self.optimizer.estimate_cost(request)
    
    def _handle_time_prediction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle time prediction request"""
        request = ManufacturingRequest(**data)
        return self.optimizer.predict_production_time(request)
    
    def _handle_manufacturer_matching(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle manufacturer matching request"""
        request = ManufacturingRequest(**data["request"])
        manufacturers = [ManufacturerProfile(**m) for m in data["manufacturers"]]
        return {"matches": self.optimizer.match_manufacturers(request, manufacturers)}
    
    def _handle_schedule_optimization(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle schedule optimization request"""
        return self.optimizer.optimize_production_schedule(data["orders"])
    
    def _handle_quality_analysis(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle quality analysis request"""
        return self.optimizer.analyze_quality_requirements(data["specifications"])


if __name__ == "__main__":
    # Example usage
    optimizer = ManufacturingOptimizer()
    
    sample_request = ManufacturingRequest(
        product_name="Custom Bracket",
        specifications="Metal bracket with precision holes",
        quantity=100,
        material="steel",
        dimensions={"length": 10, "width": 5, "height": 2},
        tolerance=0.01,
        deadline="2025-11-01"
    )
    
    cost_estimate = optimizer.estimate_cost(sample_request)
    print(f"Cost Estimate: ${cost_estimate['total_cost']}")
    
    time_prediction = optimizer.predict_production_time(sample_request)
    print(f"Production Time: {time_prediction['production_days']} days")
