package com.example.network

import android.util.Log
import io.socket.client.IO
import io.socket.client.Socket
import io.socket.emitter.Emitter

object SocketManager {

    private const val TAG = "SocketManager"
    // Socket.io 서버 URL (trailing slash 없이)
    private val SERVER_URL = RetrofitClient.BASE_URL.trimEnd('/')

    private var socket: Socket? = null

    // JWT 토큰으로 인증하며 연결 (서버에서 user:{userId} 룸 자동 참여)
    fun connect(token: String) {
        try {
            socket?.disconnect()
            val opts = IO.Options().apply {
                auth = mapOf("token" to token)
                reconnection = true
                reconnectionDelay = 1000
            }
            socket = IO.socket(SERVER_URL, opts).also { s ->
                s.on(Socket.EVENT_CONNECT)    { Log.d(TAG, "Connected: ${s.id()}") }
                s.on(Socket.EVENT_DISCONNECT) { Log.d(TAG, "Disconnected") }
                s.on(Socket.EVENT_CONNECT_ERROR) { args -> Log.e(TAG, "Connect error: ${args[0]}") }
                s.connect()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Socket init error: ${e.message}")
        }
    }

    fun on(event: String, listener: Emitter.Listener) {
        socket?.on(event, listener)
    }

    fun off(event: String) {
        socket?.off(event)
    }

    fun disconnect() {
        socket?.off()
        socket?.disconnect()
        socket = null
        Log.d(TAG, "Socket disconnected and cleaned up")
    }
}
