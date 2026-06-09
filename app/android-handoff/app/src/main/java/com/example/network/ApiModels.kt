package com.example.network

import com.google.gson.annotations.SerializedName

// ── 요청 ──────────────────────────────────────────────────────
data class RegisterRequest(
    val email: String,
    val password: String,
    val name: String,
    val phone: String,
    val user_type: String = "GENERAL",
)

data class LoginRequest(
    val email: String,
    val password: String,
)

data class CompleteOrderRequest(
    @SerializedName("robotSerialNumber") val robotSerialNumber: String,
)

// ── 응답 ──────────────────────────────────────────────────────
data class ApiResponse(
    val success: Boolean,
    val message: String,
)

data class RegisterResponse(
    val success: Boolean,
    val message: String,
    val userId: Int?,
)

data class LoginResponse(
    val success: Boolean,
    val message: String,
    val token: String?,
    val user: UserData?,
)

data class UserData(
    val id: Int,
    val email: String,
    val name: String,
    val phone: String?,
    val userType: String,
)

data class QrResponse(
    val success: Boolean,
    val qrToken: String,
    val expiresIn: Int,
    val message: String,
)

data class CompleteOrderResponse(
    val success: Boolean,
    val message: String,
    val orderId: Int?,
    val totalPrice: Int?,
)

// ── WebSocket 이벤트 ───────────────────────────────────────────
data class CartUpdatedEvent(
    val items: List<ServerCartItem>,
    val totalAmount: Int,
    val updatedAt: String,
)

data class ServerCartItem(
    val productId: Int,
    val name: String,
    val price: Int,
    val qty: Int,
)

data class RobotMatchedEvent(
    val robotSerialNumber: String,
    val status: String,
)
