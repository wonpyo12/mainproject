package com.example.network

import retrofit2.http.*

interface ApiService {

    // [MySQL] 회원가입
    @POST("api/auth/register")
    suspend fun register(@Body request: RegisterRequest): RegisterResponse

    // [MySQL] 로그인 → JWT 발급
    @POST("api/auth/login")
    suspend fun login(@Body request: LoginRequest): LoginResponse

    // [Redis] QR 세션 생성 (TTL 180초)
    @GET("api/auth/qr")
    suspend fun generateQR(
        @Header("Authorization") authHeader: String,
    ): QrResponse

    // [Redis → MySQL] 결제 완료 및 주문 이력 저장
    @POST("api/orders/complete")
    suspend fun completeOrder(
        @Header("Authorization") authHeader: String,
        @Body request: CompleteOrderRequest,
    ): CompleteOrderResponse
}
