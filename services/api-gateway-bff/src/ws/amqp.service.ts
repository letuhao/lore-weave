import { Injectable, OnModuleInit, OnModuleDestroy, Logger } from '@nestjs/common';
import * as amqp from 'amqplib';
import { v4 as uuidv4 } from 'uuid';

type EventHandler = (event: object) => void;

@Injectable()
export class AmqpService implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(AmqpService.name);
  private conn: amqp.ChannelModel | null = null;
  private channel: amqp.Channel | null = null;
  private readonly handlers = new Map<string, Set<EventHandler>>();
  private readonly queueName = `gw.events.${uuidv4()}`;

  async onModuleInit(): Promise<void> {
    const url = process.env.RABBITMQ_URL || 'amqp://guest:guest@localhost:5672/';
    await this._connect(url);
  }

  private async _connect(url: string): Promise<void> {
    try {
      this.conn    = await amqp.connect(url);
      this.channel = await this.conn.createChannel();

      await this.channel.assertExchange('loreweave.events', 'topic', { durable: true });
      await this.channel.assertQueue(this.queueName, { exclusive: true, autoDelete: true });
      await this.channel.bindQueue(this.queueName, 'loreweave.events', 'user.#');

      await this.channel.consume(this.queueName, (msg) => {
        if (!msg) return;
        try {
          const event  = JSON.parse(msg.content.toString()) as { user_id?: string };
          const userId = event.user_id;
          if (userId) {
            this.handlers.get(userId)?.forEach((cb) => cb(event));
          }
        } catch (err) {
          this.logger.error('Failed to parse event message', err);
        }
        this.channel?.ack(msg);
      });

      this.logger.log(`AMQP connected, consuming on ${this.queueName}`);

      this.conn.on('error', (err) => this.logger.error('AMQP connection error', err));
      this.conn.on('close', () => {
        this.logger.warn('AMQP connection closed, reconnecting in 5s...');
        setTimeout(() => this._connect(url), 5000);
      });
    } catch (err) {
      this.logger.error('AMQP connect failed, retrying in 5s...', err);
      setTimeout(() => this._connect(url), 5000);
    }
  }

  subscribe(userId: string, handler: EventHandler): () => void {
    // Safe to call before _connect() completes: the handler is registered in the map
    // synchronously. Once the consumer starts, it reads from this same map — so any
    // subscription made during the startup window will receive events normally.
    // The only events that could be missed are those generated in the < 5s before the
    // AMQP consumer is ready, which cannot happen in practice (no WS clients connect
    // until after startup).
    if (!this.handlers.has(userId)) {
      this.handlers.set(userId, new Set());
    }
    this.handlers.get(userId)!.add(handler);

    return () => {
      const set = this.handlers.get(userId);
      if (!set) return;
      set.delete(handler);
      if (set.size === 0) this.handlers.delete(userId);
    };
  }

  async onModuleDestroy(): Promise<void> {
    try {
      await this.channel?.close();
      await this.conn?.close();
    } catch {
      // ignore close errors on shutdown
    }
  }
}
